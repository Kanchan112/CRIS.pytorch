import os
import time

import cv2
import numpy as np
import torch
import torch.cuda.amp as amp
import torch.distributed as dist
import torch.nn.functional as F
import wandb
from loguru import logger
from tqdm import tqdm
from utils.dataset import tokenize
from utils.misc import AverageMeter, ProgressMeter, concat_all_gather, trainMetricGPU


def train(
    train_loader,
    model,
    optimizer,
    scheduler,
    scaler,
    epoch,
    args,
):
    batch_time = AverageMeter("Batch", ":2.2f")
    data_time = AverageMeter("Data", ":2.2f")
    lr = AverageMeter("Lr", ":1.6f")
    loss_meter = AverageMeter("Loss", ":2.4f")
    iou_meter = AverageMeter("IoU", ":2.2f")
    pr_meter = AverageMeter("Prec@50", ":2.2f")
    progress = ProgressMeter(
        len(train_loader),
        [batch_time, data_time, lr, loss_meter, iou_meter, pr_meter],
        prefix="Training: Epoch=[{}/{}] ".format(epoch, args.epochs),
    )

    model.train()
    time.sleep(2)
    end = time.time()

    # size_list = [320, 352, 384, 416, 448, 480, 512]
    # idx = np.random.choice(len(size_list))
    # new_size = size_list[idx]

    for i, (image, text, target) in enumerate(train_loader):
        data_time.update(time.time() - end)
        # data
        image = image.cuda(non_blocking=True)
        text = text.cuda(non_blocking=True)
        target = target.cuda(non_blocking=True).unsqueeze(1)

        # # multi-scale training
        # image = F.interpolate(image, size=(new_size, new_size), mode='bilinear')

        # forward
        with amp.autocast():
            pred, target, loss = model(image, text, target)

        # backward
        optimizer.zero_grad()
        scaler.scale(loss).backward()

        if args.max_norm:
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_norm)
        scaler.step(optimizer)
        scaler.update()

        # metric
        iou, pr5 = trainMetricGPU(pred, target, 0.35, 0.5)
        dist.all_reduce(loss.detach())
        dist.all_reduce(iou)
        dist.all_reduce(pr5)
        loss = loss / dist.get_world_size()
        iou = iou / dist.get_world_size()
        pr5 = pr5 / dist.get_world_size()

        loss_meter.update(loss.item(), image.size(0))
        iou_meter.update(iou.item(), image.size(0))
        pr_meter.update(pr5.item(), image.size(0))
        lr.update(scheduler.get_last_lr()[-1])
        batch_time.update(time.time() - end)
        end = time.time()

        if (i + 1) % args.print_freq == 0:
            progress.display(i + 1)
            # if dist.get_rank() in [-1, 0]:
            # wandb.log(
            #     {
            #         "training/epoch_loss": loss_meter.val,
            #         "training/epoch_iou": iou_meter.val,
            #         "training/epoch_prec@50": pr_meter.val,
            #         # "valid/iou": valid_epoch_iou,
            #     },
            #     step=epoch,
            # )
    return iou_meter.val, loss_meter.val


@torch.inference_mode()
def validate(val_loader, model, epoch, args, train_iou, train_loss):
    iou_list = []
    model.eval()
    time.sleep(2)
    for imgs, texts, param in val_loader:
        # data
        imgs = imgs.cuda(non_blocking=True)
        texts = texts.cuda(non_blocking=True)
        # inference
        preds = model(imgs, texts)
        preds = torch.sigmoid(preds)
        if preds.shape[-2:] != imgs.shape[-2:]:
            preds = F.interpolate(
                preds, size=imgs.shape[-2:], mode="bicubic", align_corners=True
            ).squeeze(1)
        # process one batch
        for pred, mask_dir, mat, ori_size in zip(
            preds, param["mask_dir"], param["inverse"], param["ori_size"]
        ):
            h, w = np.array(ori_size)
            mat = np.array(mat)
            pred = pred.cpu().numpy()
            pred = cv2.warpAffine(
                pred, mat, (w, h), flags=cv2.INTER_CUBIC, borderValue=0.0
            )
            pred = np.array(pred > 0.35)
            mask = cv2.imread(mask_dir, flags=cv2.IMREAD_GRAYSCALE)
            # resize
            if args.resize:
                mask = cv2.resize(mask, (224, 224))
                mask = mask / 255.0
            # iou

            inter = np.logical_and(pred, mask)
            union = np.logical_or(pred, mask)
            iou = np.sum(inter) / (np.sum(union) + 1e-6)
            iou_list.append(iou)
    iou_list = np.stack(iou_list)
    iou_list = torch.from_numpy(iou_list).to(imgs.device)
    iou_list = concat_all_gather(iou_list)
    prec_list = []
    for thres in torch.arange(0.5, 1.0, 0.1):
        tmp = (iou_list > thres).float().mean()
        prec_list.append(tmp)
    iou = iou_list.mean()
    prec = {}
    temp = "  "
    for i, thres in enumerate(range(5, 10)):
        key = "Pr@{}".format(thres * 10)
        value = prec_list[i].item()
        prec[key] = value
        temp += "{}: {:.2f}  ".format(key, 100.0 * value)
    head = "Evaluation: Epoch=[{}/{}]  IoU={:.2f}".format(
        epoch, args.epochs, 100.0 * iou.item()
    )

    logger.info(head + temp)

    if dist.get_rank() in [-1, 0]:
        wandb.log(
            {
                "training/epoch_loss": train_loss,
                "training/epoch_iou": train_iou,
                "valid/epoch_iou": iou.item(),
            },
            step=epoch,
        )
    return iou.item(), prec


@torch.inference_mode()
def inference(test_loader, model, args):
    iou_list = []
    tbar = tqdm(test_loader, desc="Inference:", ncols=100)
    model.eval()
    time.sleep(2)
    for img, param in tbar:
        # data
        img = img.cuda(non_blocking=True)
        mask = cv2.imread(param["mask_dir"][0], flags=cv2.IMREAD_GRAYSCALE)

        # resize
        h_, w_ = mask.shape
        if args.resize:
            mask = cv2.resize(mask, (224, 224))
        # dump image & mask
        if args.visualize:
            mask_name = param["mask_name"][0]

            seg_id, ext = os.path.splitext(mask_name)

            img_name = "{}-img.jpg".format(seg_id)
            mask_name = "{}-mask.png".format(seg_id)
            if args.resize:
                img_param = cv2.resize(param["ori_img"][0].cpu().numpy(), (h_, w_))
            cv2.imwrite(
                filename=os.path.join(args.vis_dir, img_name),
                img=param["ori_img"][0].cpu().numpy(),
            )
            if args.resize:
                mask = cv2.resize(mask, (h_, w_))

            output_filename = os.path.join(args.vis_dir, mask_name)

            os.makedirs(output_filename.rsplit("/", 1)[0], exist_ok=True)

            cv2.imwrite(filename=output_filename, img=mask)

            output_filename = os.path.join(args.gt_dir, "{}.png".format(seg_id))

            os.makedirs(output_filename.rsplit("/", 1)[0], exist_ok=True)

            cv2.imwrite(
                filename=output_filename, img=mask
            )
        # multiple sentences
        for sent in param["sents"]:
            mask = mask / 255.0
            text = tokenize(sent, args.word_len, True)
            text = text.cuda(non_blocking=True)
            # inference
            pred = model(img, text)
            pred = torch.sigmoid(pred)
            if pred.shape[-2:] != img.shape[-2:]:
                pred = F.interpolate(
                    pred, size=img.shape[-2:], mode="bicubic", align_corners=True
                ).squeeze()
            # process one sentence
            h, w = param["ori_size"].numpy()[0]
            mat = param["inverse"].numpy()[0]
            pred = pred.cpu().numpy()
            pred = cv2.warpAffine(
                pred, mat, (w, h), flags=cv2.INTER_CUBIC, borderValue=0.0
            )
            pred = np.array(pred > 0.35)
            # iou
            inter = np.logical_and(pred, mask)
            union = np.logical_or(pred, mask)
            iou = np.sum(inter) / (np.sum(union) + 1e-6)
            iou_list.append(iou)
            # dump prediction
            if args.visualize:
                pred = np.array(pred * 255, dtype=np.uint8)
                sent = "_".join(sent[0].split(" "))
                pred_name = "{}-iou={:.2f}-{}.png".format(seg_id, iou * 100, sent)

                output_filename = os.path.join(args.vis_dir, pred_name)

                os.makedirs(output_filename.rsplit("/", 1)[0], exist_ok=True)

                cv2.imwrite(filename=output_filename, img=pred)

                output_filename = os.path.join(args.pred_dir, "{}.png".format(seg_id))
                os.makedirs(output_filename.rsplit("/", 1)[0], exist_ok=True)
                cv2.imwrite(
                    filename=output_filename,
                    img=pred,
                )
    logger.info("=> Metric Calculation <=")
    iou_list = np.stack(iou_list)
    iou_list = torch.from_numpy(iou_list).to(img.device)
    prec_list = []
    for thres in torch.arange(0.5, 1.0, 0.1):
        tmp = (iou_list > thres).float().mean()
        prec_list.append(tmp)
    iou = iou_list.mean()
    prec = {}
    for i, thres in enumerate(range(5, 10)):
        key = "Pr@{}".format(thres * 10)
        value = prec_list[i].item()
        prec[key] = value
    logger.info("IoU={:.2f}".format(100.0 * iou.item()))
    for k, v in prec.items():
        logger.info("{}: {:.2f}.".format(k, 100.0 * v))

    return iou.item(), prec

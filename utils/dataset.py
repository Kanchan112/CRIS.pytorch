import ast
import os
from typing import List, Union

import cv2
import lmdb
import numpy as np
import pyarrow as pa
import torch
from torch.utils.data import Dataset

from .simple_tokenizer import SimpleTokenizer as _Tokenizer

info = {
    "refcoco": {
        "train": 42404,
        "val": 3811,
        "val-test": 3811,
        "testA": 1975,
        "testB": 1810,
    },
    "refcoco+": {
        "train": 42278,
        "val": 3805,
        "val-test": 3805,
        "testA": 1975,
        "testB": 1798,
    },
    "refcocog_u": {"train": 42226, "val": 2573, "val-test": 2573, "test": 5023},
    "refcocog_g": {"train": 44822, "val": 5000, "val-test": 5000},
    "kvasir_polyp": {"train": 800, "val": 100, "testA": 100, "testB": 100},
    "sessile_polyp": {"train": 196, "val": 0, "testA": 0, "testB": 0},
    "clinicdb_polyp": {"train": 612, "val": 0, "testA": 0, "testB": 0},
    "bkai_polyp": {"train": 1000, "val": 0, "testA": 0, "testB": 0},
    "kvasir_polyp_test": {"train": 0, "val": 100, "testA": 0, "testB": 0},
    "kvasir_polyp_80_10_10": {"train": 800, "val": 100, "testA": 100, "testB": 100},
    "clinicdb_polyp_80_10_10": {"train": 490, "val": 61, "testA": 61, "testB": 61},
    "bkai_polyp_80_10_10": {"train": 800, "val": 100, "testA": 100, "testB": 100},
    "cvc300_polyp_33_0_67": {"train": 0, "val": 20, "testA": 40, "testB": 40},
    "cvccolondb_polyp_51_0_949": {"train": 0, "val": 20, "testA": 360, "testB": 360},
    "etis_polyp_10_0_90": {"train": 0, "val": 20, "testA": 176, "testB": 176},
    "isic_skin_90_10_d": {"train": 800, "val": 100, "testA": 379, "testB": 379},
    "camus_80_10_10": {"train": 4320, "val": 540, "testA": 600, "testB": 600},
    "camus_80_10_10_old": {"train": 4320, "val": 540, "testA": 540, "testB": 540},
    "busi_80_10_10": {"train": 624, "val": 78, "testA": 78, "testB": 78},
    "chexlocalize_no_train": {"train": 1330, "val": 420, "testA": 427, "testB": 427},
    "cvc300_polyp_0_0_100": {"train": 0, "val": 0, "testA": 60, "testB": 60},
    "cvccolondb_polyp_0_0_100": {"train": 0, "val": 0, "testA": 380, "testB": 380},
    "etis_polyp_0_0_100": {"train": 0, "val": 0, "testA": 196, "testB": 196},
    "dfu-2022_80_10_10": {"train": 1600, "val": 200, "testA": 200, "testB": 200},
    "isic_90_10_d": {"train": 810, "val": 90, "testA": 379, "testB": 379},
    "endoscopy_all": {"train": 2090, "val": 261, "testA": 897, "testB": 897},
    "all_combined": {"train": 10723, "val": 1615, "testA": 2546, "testB": 2546},
}
_tokenizer = _Tokenizer()


def tokenize(
    texts: Union[str, List[str]], context_length: int = 77, truncate: bool = False
) -> torch.LongTensor:
    """
    Returns the tokenized representation of given input string(s)

    Parameters
    ----------
    texts : Union[str, List[str]]
        An input string or a list of input strings to tokenize

    context_length : int
        The context length to use; all CLIP models use 77 as the context length

    truncate: bool
        Whether to truncate the text in case its encoding is longer than the context length

    Returns
    -------
    A two-dimensional tensor containing the resulting tokens, shape = [number of input strings, context_length]
    """
    if isinstance(texts, str):
        texts = [texts]

    sot_token = _tokenizer.encoder["<|startoftext|>"]
    eot_token = _tokenizer.encoder["<|endoftext|>"]
    all_tokens = [[sot_token] + _tokenizer.encode(text) + [eot_token] for text in texts]
    result = torch.zeros(len(all_tokens), context_length, dtype=torch.long)

    for i, tokens in enumerate(all_tokens):
        if len(tokens) > context_length:
            if truncate:
                tokens = tokens[:context_length]
                tokens[-1] = eot_token
            else:
                raise RuntimeError(
                    f"Input {texts[i]} is too long for context length {context_length}"
                )
        result[i, : len(tokens)] = torch.tensor(tokens)

    return result


def loads_pyarrow(buf):
    """
    Args:
        buf: the output of `dumps`.
    """
    return pa.deserialize(buf)


class RefDataset(Dataset):
    def __init__(
        self,
        lmdb_dir,
        mask_dir,
        dataset,
        split,
        mode,
        input_size,
        word_length,
        prompt_type,
        resize,
    ):
        super(RefDataset, self).__init__()
        self.lmdb_dir = lmdb_dir
        self.mask_dir = mask_dir
        self.dataset = dataset
        self.split = split
        self.mode = mode
        self.input_size = (input_size, input_size)
        self.word_length = word_length
        self.mean = torch.tensor([0.48145466, 0.4578275, 0.40821073]).reshape(3, 1, 1)
        self.std = torch.tensor([0.26862954, 0.26130258, 0.27577711]).reshape(3, 1, 1)
        self.length = info[dataset][split]
        self.env = None
        self.prompt_type = prompt_type
        self.resize = resize

    def _init_db(self):
        self.env = lmdb.open(
            self.lmdb_dir,
            subdir=os.path.isdir(self.lmdb_dir),
            readonly=True,
            lock=False,
            readahead=False,
            meminit=False,
        )
        with self.env.begin(write=False) as txn:
            dgth = loads_pyarrow(txn.get(b"__len__"))
            self.keys = loads_pyarrow(txn.get(b"__keys__"))

    def __len__(self):
        return self.length

    def __getitem__(self, index):
        # Delay loading LMDB data until after initialization: https://github.com/chainer/chainermn/issues/129
        if self.env is None:
            self._init_db()
        env = self.env
        with env.begin(write=False) as txn:
            byteflow = txn.get(self.keys[index])
        ref = loads_pyarrow(byteflow)
        # img
        ori_img = cv2.imdecode(np.frombuffer(ref["img"], np.uint8), cv2.IMREAD_COLOR)
        img = cv2.cvtColor(ori_img, cv2.COLOR_BGR2RGB)
        if self.resize:
            img = cv2.resize(img, (224, 224))
        img_size = img.shape[:2]
        # mask
        mask_name = ref["mask_name"]
        mask_dir = os.path.join(self.mask_dir, mask_name)
        # sentences
        # idx = np.random.choice(ref["num_sents"])
        # idx = np.random.choice(
        #     [i for i in range(len(ref["prompts"][f"{self.prompt_type}"]))]
        # )
        # sents = ref["sents"]
        # print(ref["sents"]) # edited
        # if (
        #     self.prompt_type == "p7"
        #     or self.prompt_type == "p8"
        #     or self.prompt_type == "p9"

        # ):
        # print("&&", self.prompt_type)
        prompt_type = ""

        if self.prompt_type == "random":
            prompt_type_list = list(ref["prompts"].keys())
            prompt_type = np.random.choice(prompt_type_list)
        else:
            prompt_type = self.prompt_type

        # print("*", prompt_type)

        sents = ref["prompts"][f"{prompt_type}"]

        assert type(sents) == list or type(sents) == str, "should be list or string"

        if type(sents) != list:
            sents = [sents]
        else:
            sents = ref["prompts"][f"{prompt_type}"]  # edited
            if len(sents) == 0:  # edited
                sents = [""]  # edited
            # print(ref["prompts"][f"{self.prompt_type}"] == "")  # edited

        # if type(sents) != "list"
        # print(sents, type(sents))
        idx = np.random.choice([i for i in range(len(sents))])
        # transform
        mat, mat_inv = self.getTransformMat(img_size, True)
        img = cv2.warpAffine(
            img,
            mat,
            self.input_size,
            flags=cv2.INTER_CUBIC,
            borderValue=[0.48145466 * 255, 0.4578275 * 255, 0.40821073 * 255],
        )

        if self.mode == "train":
            # mask transform
            mask = cv2.imdecode(
                np.frombuffer(ref["mask"], np.uint8), cv2.IMREAD_GRAYSCALE
            )
            if self.resize:
                mask = cv2.resize(mask, (224, 224))
            mask = cv2.warpAffine(
                mask, mat, self.input_size, flags=cv2.INTER_LINEAR, borderValue=0.0
            )
            mask = mask / 255.0
            # sentence -> vector
            sent = sents[idx]

            word_vec = tokenize(sent, self.word_length, True).squeeze(0)
            img, mask = self.convert(img, mask)
            return img, word_vec, mask
        elif self.mode == "val":
            # sentence -> vector
            sent = sents[0]
            word_vec = tokenize(sent, self.word_length, True).squeeze(0)
            img = self.convert(img)[0]
            params = {
                "mask_dir": mask_dir,
                "inverse": mat_inv,
                "ori_size": np.array(img_size),
            }
            return img, word_vec, params
        else:
            # sentence -> vector
            img = self.convert(img)[0]
            params = {
                "ori_img": ori_img,
                "mask_name": mask_name,
                "mask_dir": mask_dir,
                "inverse": mat_inv,
                "ori_size": np.array(img_size),
                "sents": sents,
            }
            return img, params

    def getTransformMat(self, img_size, inverse=False):
        ori_h, ori_w = img_size
        inp_h, inp_w = self.input_size
        scale = min(inp_h / ori_h, inp_w / ori_w)
        new_h, new_w = ori_h * scale, ori_w * scale
        bias_x, bias_y = (inp_w - new_w) / 2.0, (inp_h - new_h) / 2.0

        src = np.array([[0, 0], [ori_w, 0], [0, ori_h]], np.float32)
        dst = np.array(
            [[bias_x, bias_y], [new_w + bias_x, bias_y], [bias_x, new_h + bias_y]],
            np.float32,
        )

        mat = cv2.getAffineTransform(src, dst)
        if inverse:
            mat_inv = cv2.getAffineTransform(dst, src)
            return mat, mat_inv
        return mat, None

    def convert(self, img, mask=None):
        # Image ToTensor & Normalize
        img = torch.from_numpy(img.transpose((2, 0, 1)))
        if not isinstance(img, torch.FloatTensor):
            img = img.float()
        img.div_(255.0).sub_(self.mean).div_(self.std)
        # Mask ToTensor
        if mask is not None:
            mask = torch.from_numpy(mask)
            if not isinstance(mask, torch.FloatTensor):
                mask = mask.float()
        return img, mask

    def __repr__(self):
        return (
            self.__class__.__name__
            + "("
            + f"db_path={self.lmdb_dir}, "
            + f"dataset={self.dataset}, "
            + f"split={self.split}, "
            + f"mode={self.mode}, "
            + f"input_size={self.input_size}, "
            + f"word_length={self.word_length}"
        )

    # def get_length(self):
    #     return self.length

    # def get_sample(self, idx):
    #     return self.__getitem__(idx)

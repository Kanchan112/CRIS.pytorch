#!/bin/bash
for i in {0..6}
do
    python -u test.py --config config/chexlocalize/chexlocalize_no_train.yaml --opts TEST.test_split testA TEST.test_lmdb datasets/lmdb/chexlocalize_no_train/testA.lmdb TRAIN.prompt_type p$i TRAIN.output_folder exp/chexlocalize_no_train_p${i}_fn TRAIN.resume exp/chexlocalize_no_train_p${i}_fn/CRIS_R50/best_model.pth
done

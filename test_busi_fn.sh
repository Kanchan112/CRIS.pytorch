#!/bin/bash
for i in {0..6}
do
    python -u test.py --config config/cris_r50_busi_80_10_10.yaml --opts TEST.test_split testA TEST.test_lmdb datasets/lmdb/busi_80_10_10/testA.lmdb TRAIN.prompt_type p$i TRAIN.output_folder exp/busi_80_10_10_p${i}_fn TRAIN.resume exp/busi_80_10_10_p${i}_fn/CRIS_R50/best_model.pth
done

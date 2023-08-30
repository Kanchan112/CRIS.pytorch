#!/bin/bash
model_folder="exp/busi_80_10_10_p"

for i in {0..6}
do
    model_subfolder="${model_folder}${i}_fn"
    # model_subfolder="${model_folder}${i}_fn_frozen"
    model_path="${model_subfolder}/CRIS_R50/"
    model_file="${model_path}best_model.pth"

    python -u test.py --config config/cris_r50_busi_80_10_10.yaml --opts TEST.test_split testA TEST.test_lmdb datasets/lmdb/busi_80_10_10/testA.lmdb TRAIN.prompt_type p$i TRAIN.output_folder $model_subfolder TRAIN.resume $model_file
done

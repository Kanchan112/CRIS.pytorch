#!/bin/bash

model_folder="exp/camus_80_10_10_p"

for i in {0..7}
do
    model_subfolder="${model_folder}${i}_fn"
    model_path="${model_subfolder}/CRIS_R50/"
    model_file="${model_path}best_model.pth"

    if [ ! -f "$model_file" ]; then
        model_file="${model_path}last_model.pth"
        echo "Best model not found for ${model_subfolder}. Falling back to last model."
    fi

    python -u test.py --config config/cris_r50_camus_80_10_10.yaml --opts TEST.test_split testA TEST.test_lmdb datasets/lmdb/camus_80_10_10/testA.lmdb TRAIN.prompt_type p$i TRAIN.output_folder $model_subfolder TRAIN.resume $model_file
done


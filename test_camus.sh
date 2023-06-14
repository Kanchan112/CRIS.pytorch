#!/bin/bash
for i in {0..7}
do
    python -u test.py --config config/cris_r50_camus_80_10_10.yaml --opts TEST.test_split testA TEST.test_lmdb datasets/lmdb/camus_80_10_10/testA.lmdb TRAIN.prompt_type p$i TRAIN.output_folder exp/camus_80_10_10_p"$i"_i
done

#!/bin/bash
for i in {0..6}
do
    python -u test.py --config config/cris_r50_camus_80_10_10.yaml --opts TEST.test_split testA TEST.test_lmdb datasets/lmdb/camus_80_10_10/testA.lmdb TRAIN.prompt_type p$i
done

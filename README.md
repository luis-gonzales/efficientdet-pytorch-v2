# EfficientDet (PyTorch)

A PyTorch implementation of EfficientDet.

It is based on the
* official Tensorflow implementation by [Mingxing Tan and the Google Brain team](https://github.com/google/automl)
* paper by Mingxing Tan, Ruoming Pang, Quoc V. Le [EfficientDet: Scalable and Efficient Object Detection](https://arxiv.org/abs/1911.09070) 

There are other PyTorch implementations. Either their approach didn't fit my aim to correctly reproduce the Tensorflow models (but with a PyTorch feel and flexibility) or they cannot come close to replicating MS COCO training from scratch.

Aside from the default model configs, there is a lot of flexibility to facilitate experiments and rapid improvements here -- some options based on the official Tensorflow impl, some of my own:
* BiFPN connections and combination mode are fully configurable and not baked into the model code
* BiFPN and head modules can be switched between depthwise separable or standard convolutions
* Activations, batch norm layers are switchable via arguments (soon config)
* Any backbone in my `timm` model collection that supports feature extraction (`features_only` arg) can be used as a bacbkone.

## Updates

### 2023-05-21
* Depend on `timm` 0.9
* Minor bug fixes
* Version 0.4.1 release

### 2023-02-09
* Testing with PyTorch 2.0 (nightlies), add --torchcompile support to train and validate scripts
* A small code cleanup pass, support bwd/fwd compat across timm 0.8.x and previous releases
* Use `timm` convert_sync_batchnorm function as it handles updated models w/ BatchNormAct2d layers

### 2022-01-06
* New `efficientnetv2_ds` weights 50.1 mAP @ 1024x0124, using AGC clipping and `timm`'s `efficientnetv2_rw_s` backbone. Memory use comparable to D3, speed faster than D4. Smaller than optimal training batch size so can probably do better... 

### 2021-11-30
* Update `efficientnetv2_dt` weights to a new set, 46.1 mAP @ 768x768, 47.0 mAP @ 896x896 using AGC clipping.
* Add AGC (Adaptive Gradient Clipping support via `timm`). Idea from (`High-Performance Large-Scale Image Recognition Without Normalization` - https://arxiv.org/abs/2102.06171)
* `timm` minimum version bumped up to 0.4.12

### 2021-11-16
* Add EfficientNetV2 backbone experiment `efficientnetv2_dt` based on `timm`'s `efficientnetv2_rw_t` (tiny) model. 45.8 mAP @ 768x768.
* Updated TF EfficientDet-Lite model defs incl weights ported from official impl (https://github.com/google/automl)
* For Lite models, updated feature resizing code in FPN to be based on feat size instead of reduction ratios, needed to support image size that aren't divisible by 128.
* Minor tweaks, bug fixes

### 2021-07-28
* Add training example to README provided by Chris Hughes for training w/ custom dataset & Lightning training code
  * [Medium blog post](https://medium.com/data-science-at-microsoft/training-efficientdet-on-custom-data-with-pytorch-lightning-using-an-efficientnetv2-backbone-1cdf3bd7921f)
  * [Python notebook](https://gist.github.com/Chris-hughes10/73628b1d8d6fc7d359b3dcbbbb8869d7)

### 2021-04-30
* Add EfficientDet AdvProp-AA weights for D0-D5 from TF impl. Model names `tf_efficientdet_d?_ap`
  * See https://github.com/google/automl/blob/master/efficientdet/Det-AdvProp.md

### 2021-02-18
* Add some new model weights with bilinear interpolation for upsample and downsample in FPN.
  * 40.9 mAP - `efficientdet_q1`  (replace prev model at 40.6)
  * 43.2 mAP -`cspresdet50`
  * 45.2 mAP - `cspdarkdet53m`

### 2020-12-07
* Training w/ fully jit scripted model + bench (`--torchscript`) is possible with inclusion of ModelEmaV2 from `timm` and previous torchscript compat additions. Big speed gains for CPU bound training.
* Add weights for alternate FPN layouts. QuadFPN experiments (`efficientdet_q0/q1/q2`) and CSPResDeXt + PAN (`cspresdext50pan`). See updated table below. Special thanks to [Artus](https://twitter.com/artuskg) for providing resources for training the Q2 model.
* Heads can have a different activation from FPN via config
* FPN resample (interpolation) can be specified via config and include any F.interpolation method or `max`/`avg` pool
* Default focal loss changed back to `new_focal`, use `--legacy-focal` arg to use the original. Legacy uses less memory, but has more numerical stability issues.
* custom augmentation transform and collate fn can be passed to loader factory
* `timm` >= 0.3.2 required, NOTE double check any custom defined model config for breaking change 
* PyTorch >= 1.6 now required

### 2020-11-12
* add experimental PAN and Quad FPN configs to the existing EfficientDet BiFPN w/ two test model configs
* switch untrained experimental model configs to use torchscript compat bn head layout by default

### 2020-11-09
* set model config to read-only after creation to reduce likelyhood of misuse
* no accessing model or bench .config attr in forward() call chain (for torcscript compat)
* numerous smaller changes that allow jit scripting of the model or train/predict bench

### 2020-10-30
Merged a few months of accumulated fixes and additions.
* Proper fine-tuning compatible model init (w/ changeable # classes and proper init, demoed in train.py)
* A new dataset interface with dataset support (via parser classes) for COCO, VOC 2007/2012, and OpenImages V5/Challenge2019
* New focal loss def w/ label smoothing available as an option, support for jit of loss fn for (potential) speedup
* Improved a few hot spots that squeek out a couple % of throughput gains, higher GPU utilization
* Pascal / OpenImages evaluators based on Tensorflow Models Evaluator framework (usable for other datasets as well)
* Support for native PyTorch DDP, SyncBN, and AMP in PyTorch >= 1.6. Still defaults to APEX if installed.
* Non-square input image sizes are allowed for the model (the anchor layout). Specified by image_size tuple in model config. Currently still restricted to `size % 128 = 0` on each dim.
* Allow anchor target generation to be done in either dataloader process' via collate or in model as in past. Can help balance compute.
* Filter out unused target cls/box from dataset annotations in fixed size batch tensors before passing to target assigner. Seems to speed convergence.
* Letterbox aware Random Erasing augmentation added.
* A (very slow) SoftNMS impl added for inference/validation use. It can be manually enabled right now, can add arg if demand.
* Tested with PyTorch 1.7
* Add ResDet50 model weights, 41.6 mAP.

A few things on priority list I haven't tackled yet:
* Mosaic augmentation
* bbox IOU loss (tried a bit but so far not a great result, need time to debug/improve)

**NOTE** There are some breaking changes:
* Predict and Train benches now output XYXY boxes, NOT XYWH as before. This was done to support other datasets as XYWH is COCO's evaluator requirement.
* The TF Models Evaluator operates on YXYX boxes like the models. Conversion from XYXY is currently done by default. Why don't I just keep everything YXYX? Because PyTorch GPU NMS operates in XYXY.
* You must update your version of `timm` to the latest (>=0.3), as some APIs for helpers changed a bit.

Training sanity checks were done on VOC and OI
  * 80.0 @ 50 mAP finetune on voc0712 with no attempt to tune params (roughly as per command below)
  * 18.0 mAP @ 50 for OI Challenge2019 after couple days of training (only 6 epochs, eek!). It's much bigger, and takes a LOONG time, many classes are quite challenging.


## Environment Setup

Tested in a Python 3.7 - 3.9 conda environment in Linux with:
* PyTorch 1.6 - 1.10
* PyTorch Image Models (timm) >= 0.4.12, `pip install timm` or local install from (https://github.com/rwightman/pytorch-image-models)
* Apex AMP master (as of 2020-08). I recommend using native PyTorch AMP and DDP now.

*NOTE* - There is a conflict/bug with Numpy 1.18+ and pycocotools 2.0, force install numpy <= 1.17.5 or ensure you install pycocotools >= 2.0.2

## Dataset Setup and Use

### COCO
MSCOCO 2017 validation data:
```
wget http://images.cocodataset.org/zips/val2017.zip
wget http://images.cocodataset.org/annotations/annotations_trainval2017.zip
unzip val2017.zip
unzip annotations_trainval2017.zip
```

MSCOCO 2017 test-dev data:
```
wget http://images.cocodataset.org/zips/test2017.zip
unzip -q test2017.zip
wget http://images.cocodataset.org/annotations/image_info_test2017.zip
unzip image_info_test2017.zip
```

#### COCO Evaluation

Run validation (val2017 by default) with D2 model: `python validate.py /localtion/of/mscoco/ --model tf_efficientdet_d2`


Run test-dev2017: `python validate.py /localtion/of/mscoco/ --model tf_efficientdet_d2 --split testdev`

#### COCO Training

`./distributed_train.sh 4 /mscoco --model tf_efficientdet_d0 -b 16 --amp  --lr .09 --warmup-epochs 5  --sync-bn --opt fusedmomentum --model-ema`

NOTE:
* Training script currently defaults to a model that does NOT have redundant conv + BN bias layers like the official models, set correct flag when validating.
* I've only trained with img mean (`--fill-color mean`) as the background for crop/scale/aspect fill, the official repo uses black pixel (0) (`--fill-color 0`). Both likely work fine.
* The official training code uses EMA weight averaging by default, it's not clear there is a point in doing this with the cosine LR schedule, I find the non-EMA weights end up better than EMA in the last 10-20% of training epochs 
* The default h-params is a very close to unstable (exploding loss), don't try using Nesterov momentum. Try to keep the batch size up, use sync-bn.


### OpenImages

Setting up OpenImages dataset is a commitment. I've tried to make it a bit easier wrt to the annotations, but grabbing the dataset is still going to take some time. It will take approx 560GB of storage space.

To download the image data, I prefer the CVDF packaging. The main OpenImages dataset page, annotations, dataset license info can be found at: https://storage.googleapis.com/openimages/web/index.html

#### CVDF Images Download

Follow the s3 download directions here: https://github.com/cvdfoundation/open-images-dataset#download-images-with-bounding-boxes-annotations

Each `train_<x>.tar.gz` should be extracted to `train/<x>` folder, where x is a hex digit from 0-F. `validation.tar.gz` can be extracted as flat files into `validation/`.

#### Annotations Download

Annotations can be downloaded separately from the OpenImages home page above. For convenience, I've packaged them all together with some additional 'info' csv files that contain ids and stats for all image files. My datasets rely on the `<set>-info.csv` files. Please see https://storage.googleapis.com/openimages/web/factsfigures.html for the License of these annotations. The annotations are licensed by Google LLC under CC BY 4.0 license. The images are listed as having a CC BY 2.0 license.
```
wget https://github.com/rwightman/efficientdet-pytorch/releases/download/v0.1-anno/openimages-annotations.tar.bz2
wget https://github.com/rwightman/efficientdet-pytorch/releases/download/v0.1-anno/openimages-annotations-challenge-2019.tar.bz2
find . -name '*.tar.bz2' -exec tar xf {} \;
```

#### Layout

Once everything is downloaded and extracted the root of your openimages data folder should contain:
```
annotations/<csv anno for openimages v5/v6>
annotations/challenge-2019/<csv anno for challenge2019>
train/0/<all the image files starting with '0'>
.
.
.
train/f/<all the image files starting with 'f'>
validation/<all the image files in same folder>
```

#### OpenImages Training
Training with Challenge2019 annotations (500 classes):
`./distributed_train.sh 4 /data/openimages --model efficientdet_d0 --dataset openimages-challenge2019 -b 7 --amp --lr .042 --sync-bn --opt fusedmomentum --warmup-epochs 1 --lr-noise 0.4 0.9 --model-ema --model-ema-decay 0.999966 --epochs 100 --remode pixel --reprob 0.15 --recount 4 --num-classes 500 --val-skip 2`

The 500 (Challenge2019) or 601 (V5/V6) class head for OI takes up a LOT more GPU memory vs COCO. You'll likely need to half batch sizes.

### Examples of Training / Fine-Tuning on Custom Datasets

The models here have been used with custom training routines and datasets with great results. There are lots of details to figure out so please don't file any 'I get crap results on my custom dataset issues'. If you can illustrate a reproducible problem on a public, non-proprietary, downloadable dataset, with public github fork of this repo including working dataset/parser implementations, I MAY have time to take a look.

Examples:
* Chris Hughes has put together a great example of training w/ `timm` EfficientNetV2 backbones and the latest versions of the EfficientDet models here
  * [Medium blog post](https://medium.com/data-science-at-microsoft/training-efficientdet-on-custom-data-with-pytorch-lightning-using-an-efficientnetv2-backbone-1cdf3bd7921f)
  * [Python notebook](https://gist.github.com/Chris-hughes10/73628b1d8d6fc7d359b3dcbbbb8869d7)
* Alex Shonenkov has a clear and concise Kaggle kernel which illustrates fine-tuning these models for detecting wheat heads: https://www.kaggle.com/shonenkov/training-efficientdet (NOTE: this is out of date wrt to latest versions here, many details have changed)

If you have a good example script or kernel training these models with a different dataset, feel free to notify me for inclusion here...

## Results

### My Training

#### EfficientDet-D0

Latest training run with .336 for D0 (on 4x 1080ti):
`./distributed_train.sh 4 /mscoco --model efficientdet_d0 -b 22 --amp --lr .12 --sync-bn --opt fusedmomentum --warmup-epochs 5 --lr-noise 0.4 0.9 --model-ema --model-ema-decay 0.9999`

These hparams above resulted in a good model, a few points:
* the mAP peaked very early (epoch 200 of 300) and then appeared to overfit, so likely still room for improvement
* I enabled my experimental LR noise which tends to work well with EMA enabled
* the effective LR is a bit higher than official. Official is .08 for batch 64, this works out to .0872
* drop_path (aka survival_prob / drop_connect) rate of 0.1, which is higher than the suggested 0.0 for D0 in official, but lower than the 0.2 for the other models
* longer EMA period than default

VAL2017
```
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.336251
 Average Precision  (AP) @[ IoU=0.50      | area=   all | maxDets=100 ] = 0.521584
 Average Precision  (AP) @[ IoU=0.75      | area=   all | maxDets=100 ] = 0.356439
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.123988
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.395033
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.521695
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=  1 ] = 0.287121
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets= 10 ] = 0.441450
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.467914
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.197697
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.552515
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.689297
```

#### EfficientDet-D1 

Latest run with .394 mAP (on 4x 1080ti):
`./distributed_train.sh 4 /mscoco --model efficientdet_d1 -b 10 --amp --lr .06 --sync-bn --opt fusedmomentum --warmup-epochs 5 --lr-noise 0.4 0.9 --model-ema --model-ema-decay 0.99995`

For this run I used some improved augmentations, still experimenting so not ready for release, should work well without them but will likely start overfitting a bit sooner and possibly end up a in the .385-.39 range.


### Ported Tensorflow weights

#### TEST-DEV2017

NOTE: I've only tried submitting D7 to dev server for sanity check so far

##### TF-EfficientDet-D7
```
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.534
 Average Precision  (AP) @[ IoU=0.50      | area=   all | maxDets=100 ] = 0.726
 Average Precision  (AP) @[ IoU=0.75      | area=   all | maxDets=100 ] = 0.577
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.356
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.569
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.660
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=  1 ] = 0.397
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets= 10 ] = 0.644
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.682
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.508
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.718
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.818
 ```

#### VAL2017

##### TF-EfficientDet-D0
```
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.341877
 Average Precision  (AP) @[ IoU=0.50      | area=   all | maxDets=100 ] = 0.525112
 Average Precision  (AP) @[ IoU=0.75      | area=   all | maxDets=100 ] = 0.360218
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.131366
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.399686
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.537368
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=  1 ] = 0.293137
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets= 10 ] = 0.447829
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.472954
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.195282
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.558127
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.695312
```

##### TF-EfficientDet-D1
```
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.401070
 Average Precision  (AP) @[ IoU=0.50      | area=   all | maxDets=100 ] = 0.590625
 Average Precision  (AP) @[ IoU=0.75      | area=   all | maxDets=100 ] = 0.422998
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.211116
 Average Precision  (AP) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.459650
 Average Precision  (AP) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.577114
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=  1 ] = 0.326565
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets= 10 ] = 0.507095
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=   all | maxDets=100 ] = 0.537278
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= small | maxDets=100 ] = 0.308963
 Average Recall     (AR) @[ IoU=0.50:0.95 | area=medium | maxDets=100 ] = 0.610450
 Average Recall     (AR) @[ IoU=0.50:0.95 | area= large | maxDets=100 ] = 0.731814
```

## TODO
- [x] Basic Training (object detection) reimplementation
- [ ] Mosaic Augmentation
- [ ] Rand/AutoAugment
- [ ] Training (semantic segmentation) experiments
- [ ] Integration with Detectron2 / MMDetection codebases
- [ ] Addition and cleanup of EfficientNet based U-Net and DeepLab segmentation models that I've used in past projects
- [x] Addition and cleanup of OpenImages dataset/training support from a past project
- [ ] Exploration of instance segmentation possibilities...

If you are an organization is interested in sponsoring and any of this work, or prioritization of the possible future directions interests you, feel free to contact me (issue, LinkedIn, Twitter, hello at rwightman dot com). I will setup a github sponser if there is any interest.

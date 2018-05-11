# Image Colorization with Generative Adversarial Networks 
In this repo, we generalize the colorization procedure using a conditional Deep Convolutional Generative Adversarial Network (DCGAN) as as suggested by [Pix2Pix]. The network is trained on the datasets [CIFAR-10](https://www.cs.toronto.edu/~kriz/cifar.html) and [Places365](http://places2.csail.mit.edu). Some of the results from Places365 dataset are [shown here.](#places365-results)

## Prerequisites
- Linux
- Tensorflow 1.7
- NVIDIA GPU (12G or 24G memory) + CUDA cuDNN

## Getting Started
### Installation
- Install Tensorflow and dependencies from https://www.tensorflow.org/install/
- Clone this repo:
```bash
git clone https://github.com/ImagingLab/Colorizing-with-GANs.git
cd Colorizing-with-GANs
```

### Dataset
- We use [CIFAR-10](https://www.cs.toronto.edu/~kriz/cifar.html) and [Places365](http://places2.csail.mit.edu) datasets. To train a model on the full dataset, download datasets from official websites.
After downloading, put then under the `datasets` folder.

### Training
- To train the model, run `main.py` script
```bash
python train.py
```
- To change the default settings:
```
python train.py \
  --seed [random seed] \
  --color-space [RGB|LAB] \
  --dataset [cifar10|places365] \
  --dataset-path [path to the dataset] \
  --checkpoints-path [path to save models] \
  --samples-path [path to save samples] \
  --batch-size [input batch size for training] \
  --epochs [umber of epochs to train] \
  --lr [learning rate] \
  --lr-decay-rate [learning rate decay rate] \
  --lr-decay-steps [learning rate decay steps] \
  --beta1 [momentum term of adam optimizer] \
  --l1-weight [weight on L1 term for generator gradient] \
  --augment [augment dataset] \
  --acc-thresh [accuracy threshold] \
  --save-interval [number of batches before saving the model] \
  --log-interval [number of batches before logging training status] \
  --gpu-ids [gpu ids for training]
  
```

## Method

### Generative Adversarial Network
Both generator and discriminator use CNNs. The generator is trained to minimize the probability that the discriminator makes a correct prediction in generated data, while discriminator is trained to maximize the probability of assigning the correct label. This is presented as a single minimax game problem:
<p align='center'>  
  <img src='img/gan.png' />
</p>
In our model, we have redefined the generator's cost function by maximizing the probability of the discriminator being mistaken, as opposed to minimizing the probability of the discriminator being correct. In addition, the cost function was further modified by adding an L1 based regularizer. This will theoretically preserve the structure of the original images and prevent the generator from assigning arbitrary colors to pixels just to fool the discriminator:
<p align='center'>  
  <img src='img/gan_new.png' />
</p>

### Conditional GAN
In a traditional GAN, the input of the generator is randomly generated noise data z. However, this approach is not applicable to the automatic colorization problem due to the nature of its inputs. The generator must be modified to accept grayscale images as inputs rather than noise. This problem was addressed by using a variant of GAN called [conditional generative adversarial networks](https://arxiv.org/abs/1411.1784). Since no noise is introduced, the input of the generator is treated as zero noise with the grayscale input as a prior:
<p align='center'>  
  <img src='img/con_gan.png' />
</p>
The discriminator gets colored images from both generator and original data along with the grayscale input as the condition and tries to tell which pair contains the true colored image:
<p align='center'>  
  <img src='img/cgan.png' />
</p>

### Networks Architecture
The architecture of generator is inspired by  [U-Net](https://arxiv.org/abs/1505.04597):  The architecture of the model is symmetric, with `n` encoding units and `n` decoding units. The contracting path consists of 4x4 convolution layers with stride 2 for downsampling, each followed by batch normalization and Leaky-ReLU activation function with the slope of 0.2. The number of channels are doubled after each step. Each unit in the expansive path consists of a 4x4 transposed convolutional layer with stride 2 for upsampling, concatenation with the activation map of the mirroring layer in the contracting path, followed by batch normalization and ReLU activation function. The last layer of the network is a 1x1 convolution which is equivalent to cross-channel parametric pooling layer. We use `tanh` function for the last layer.
<p align='center'>  
  <img src='img/unet.png' width='950px' height='228px' />
</p>

For discriminator, we use similar architecture as the baselines contractive path: a series of 4x4 convolutional layers with stride 2 with the number of channels being doubled after each downsampling. All convolution layers are followed by batch normalization, leaky ReLU activation with slope 0.2. After the last layer, a convolution is applied to map to a 1 dimensional output, followed by a sigmoid function to return a probability value of the input being real or fake
<p align='center'>  
  <img src='img/discriminator.png' width='510px' height='190px' />
</p>
  
## Citation
If you use this code for your research, please cite our paper <a href="https://arxiv.org/abs/1803.05400">Image Colorization with Generative Adversarial Networks</a>:

```
@article{nazeri2018image,
  title={Image Colorization with Generative Adversarial Networks},
  author={Nazeri, Kamyar and Ng, Eric},
  journal={arXiv preprint arXiv:1803.05400},
  year={2018}
}
```
  
## Places365 Results
Colorization results with Places365. (a) Grayscale. (b) Original Image. (c) Colorized with GAN.
<p align='center'>  
  <img src='img/places365.jpg' />
</p>


from __future__ import print_function

import os
import time
import numpy as np
import tensorflow as tf

from tensorflow import keras
from abc import abstractmethod
from .networks import Generator, Discriminator
from .dataset import CIFAR10_DATASET, PLACES365_DATASET
from .dataset import Places365Dataset, Cifar10Dataset
from .ops import pixelwise_accuracy, preprocess, postprocess
from .ops import COLORSPACE_RGB, COLORSPACE_LAB
from .utils import stitch_images, imshow, visualize


class BaseModel:
    def __init__(self, sess, options):
        self.sess = sess
        self.options = options
        self.name = options.name
        self.samples_dir = os.path.join(options.checkpoints_path, 'samples')
        self.test_log_file = os.path.join(options.checkpoints_path, 'log_test.dat')
        self.train_log_file = os.path.join(options.checkpoints_path, 'log_train.dat')
        self.global_step = tf.Variable(0, name='global_step', trainable=False)
        self.dataset_train = self.create_dataset(True)
        self.dataset_test = self.create_dataset(False)
        self.sample_generator = self.dataset_test.generator(options.sample_size, True)
        self.iteration = 0
        self.epoch = 0
        self.is_built = False

    def train(self):
        self.build()

        total = len(self.dataset_train)

        for epoch in range(self.options.epochs):
            lr_rate = self.sess.run(self.learning_rate)

            print('Training epoch: %d' % (epoch + 1) + " - learning rate: " + str(lr_rate))

            self.epoch = epoch + 1
            self.iteration = 0

            generator = self.dataset_train.generator(self.options.batch_size)
            progbar = keras.utils.Progbar(total, stateful_metrics=['epoch', 'iteration', 'step'])

            for input_rgb in generator:
                self.iteration += 1
                feed_dic = {self.input_rgb: input_rgb}

                self.sess.run([self.dis_train], feed_dict=feed_dic)
                self.sess.run([self.gen_train, self.accuracy], feed_dict=feed_dic)
                self.sess.run([self.gen_train, self.accuracy], feed_dict=feed_dic)

                errD_fake, errD_real, errG_l1, errG_gan, acc, step = self.eval_outputs(feed_dic=feed_dic)

                progbar.add(len(input_rgb), values=[
                    ("epoch", epoch + 1),
                    ("iteration", self.iteration),
                    ("step", step),
                    ("D loss", errD_fake + errD_real),
                    ("D fake", errD_fake),
                    ("D real", errD_real),
                    ("G loss", errG_l1 + errG_gan),
                    ("G L1", errG_l1),
                    ("G gan", errG_gan),
                    ("accuracy", acc)
                ])

                # log model at checkpoints
                if self.options.log and step % self.options.log_interval == 0:
                    with open(self.train_log_file, 'a') as f:
                        f.write('%d %d %f %f %f %f %f\n' % (self.epoch, step, errD_fake, errD_real, errG_l1, errG_gan, acc))

                    if self.options.visualize:
                        visualize(self.train_log_file, self.test_log_file, self.options.visualize_window, self.name)

                # sample model at checkpoints
                if self.options.sample and step % self.options.sample_interval == 0:
                    self.sample(show=False)

                # evaluate model at checkpoints
                if self.options.validate and self.options.validate_interval > 0 and step % self.options.validate_interval == 0:
                    self.evaluate()

                # save model at checkpoints
                if self.options.save and step % self.options.save_interval == 0:
                    self.save()

            if self.options.validate:
                self.evaluate()

    def evaluate(self):
        print('\n\nEvaluating epoch: %d' % self.epoch)
        test_total = len(self.dataset_test)
        test_generator = self.dataset_test.generator(self.options.batch_size)
        progbar = keras.utils.Progbar(test_total)

        result = []

        for input_rgb in test_generator:
            feed_dic = {self.input_rgb: input_rgb}

            self.sess.run([self.dis_loss, self.gen_loss, self.accuracy], feed_dict=feed_dic)
            # errD_fake, errD_real, errG_l1, errG_gan, acc, step = self.eval_outputs(feed_dic=feed_dic)
            result.append(self.eval_outputs(feed_dic=feed_dic))
            progbar.add(len(input_rgb))

        result = np.mean(np.array(result), axis=0)
        print('Results: D loss: %f - D fake: %f - D real: %f - G loss: %f - G L1: %f - G gan: %f - accuracy: %f'
              % (result[0] + result[1], result[0], result[1], result[2] + result[3], result[2], result[3], result[4]))

        if self.options.log:
            with open(self.test_log_file, 'a') as f:
                f.write('%d %d %f %f %f %f %f\n' % (self.epoch, result[5], result[0], result[1], result[2], result[3], result[4]))

        print('\n')

    def sample(self, show=True):
        self.build()

        input_rgb = next(self.sample_generator)
        feed_dic = {self.input_rgb: input_rgb}

        step, rate = self.sess.run([self.global_step, self.learning_rate])
        fake_image, input_gray = self.sess.run([self.sampler, self.input_gray], feed_dict=feed_dic)
        fake_image = postprocess(tf.convert_to_tensor(fake_image), colorspace_in=self.options.color_space, colorspace_out=COLORSPACE_RGB)
        img = stitch_images(input_gray, input_rgb, fake_image.eval())

        if not os.path.exists(self.samples_dir):
            os.makedirs(self.samples_dir)

        sample = self.options.dataset + "_" + str(step).zfill(5) + ".png"

        if show:
            imshow(np.array(img), self.name)
        else:
            print('\nsaving sample ' + sample + ' - learning rate: ' + str(rate))
            img.save(os.path.join(self.samples_dir, sample))

    def build(self):
        if self.is_built:
            return

        self.is_built = True

        # create models
        gen = self.create_generator()
        dis = self.create_discriminator()
        sce = tf.nn.sigmoid_cross_entropy_with_logits
        smoothing = 0.9 if self.options.label_smoothing else 1
        seed = seed = self.options.seed
        kernel = self.options.kernel_size

        input_shape = self.get_input_shape()
        
        self.input_rgb = tf.placeholder(tf.float32, shape=(None, input_shape[0], input_shape[1], input_shape[2]), name='input_rgb')
        self.input_gray = tf.image.rgb_to_grayscale(self.input_rgb)
        self.input_color = preprocess(self.input_rgb, colorspace_in=COLORSPACE_RGB, colorspace_out=self.options.color_space)

        self.dis = dis.create(inputs=tf.concat([self.input_gray, self.input_color], 3), kernel_size=kernel, seed=seed)
        self.gen = gen.create(inputs=self.input_gray, kernel_size=kernel, seed=seed)
        self.gan = dis.create(inputs=tf.concat([self.input_gray, self.gen], 3), reuse_variables=True, kernel_size=kernel, seed=seed)
        self.sampler = gen.create(inputs=self.input_gray, reuse_variables=True, kernel_size=kernel, seed=seed)

        self.dis_loss_real = tf.reduce_mean(sce(logits=self.dis, labels=tf.ones_like(self.dis) * smoothing))
        self.dis_loss_fake = tf.reduce_mean(sce(logits=self.gan, labels=tf.zeros_like(self.gan)))
        self.dis_loss = self.dis_loss_real + self.dis_loss_fake

        self.gen_loss_gan = tf.reduce_mean(sce(logits=self.gan, labels=tf.ones_like(self.gan)))
        self.gen_loss_l1 = tf.reduce_mean(tf.abs(self.input_color - self.gen)) * self.options.l1_weight
        self.gen_loss = self.gen_loss_gan + self.gen_loss_l1

        self.accuracy = pixelwise_accuracy(self.input_color, self.gen, self.options.color_space, self.options.acc_thresh)
        self.learning_rate = tf.constant(self.options.lr)

        if self.options.lr_decay_rate > 0:
            self.learning_rate = tf.maximum(1e-8, tf.train.exponential_decay(
                learning_rate=self.options.lr,
                global_step=self.global_step,
                decay_steps=self.options.lr_decay_steps,
                decay_rate=self.options.lr_decay_rate))

        # generator optimizaer
        self.gen_train = tf.train.AdamOptimizer(
            learning_rate=self.learning_rate,
            beta1=self.options.beta1
        ).minimize(self.gen_loss, var_list=gen.var_list)

        # discriminator optimizaer
        self.dis_train = tf.train.AdamOptimizer(
            learning_rate=self.learning_rate,
            beta1=self.options.beta1
        ).minimize(self.dis_loss, var_list=dis.var_list, global_step=self.global_step)

        self.saver = tf.train.Saver()

    def load(self):
        ckpt = tf.train.get_checkpoint_state(self.options.checkpoints_path)
        if ckpt is not None:
            print('loading model...\n')
            ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
            self.saver.restore(self.sess, os.path.join(self.options.checkpoints_path, ckpt_name))
            return True

        return False

    def save(self):
        print('saving model...\n')
        self.saver.save(self.sess, os.path.join(self.options.checkpoints_path, 'CGAN_' + self.options.dataset), write_meta_graph=False)

    def eval_outputs(self, feed_dic):
        errD_fake = self.dis_loss_fake.eval(feed_dict=feed_dic)
        errD_real = self.dis_loss_real.eval(feed_dict=feed_dic)

        errG_l1 = self.gen_loss_l1.eval(feed_dict=feed_dic)
        errG_gan = self.gen_loss_gan.eval(feed_dict=feed_dic)

        acc = self.accuracy.eval(feed_dict=feed_dic)
        step = self.sess.run(self.global_step)

        return errD_fake, errD_real, errG_l1, errG_gan, acc, step

    @abstractmethod
    def get_input_shape(self):
        raise NotImplementedError

    @abstractmethod
    def create_generator(self):
        raise NotImplementedError

    @abstractmethod
    def create_discriminator(self):
        raise NotImplementedError

    @abstractmethod
    def create_dataset(self, training):
        raise NotImplementedError


class Cifar10Model(BaseModel):
    def __init__(self, sess, options):
        super(Cifar10Model, self).__init__(sess, options)

    def get_input_shape(self):
        return (32, 32, 3)

    def create_generator(self):
        kernels_gen_encoder = [
            (64, 1, 0),     # [batch, 32, 32, ch] => [batch, 32, 32, 64]
            (64, 1, 0),     # [batch, 32, 32, 64] => [batch, 32, 32, 64]
            (128, 2, 0),    # [batch, 32, 32, 64] => [batch, 16, 16, 128]
            (256, 2, 0),    # [batch, 16, 16, 128] => [batch, 8, 8, 256]
            (512, 2, 0),    # [batch, 8, 8, 256] => [batch, 4, 4, 512]
            (1024, 2, 0)     # [batch, 4, 4, 512] => [batch, 2, 2, 1024]
        ]

        kernels_gen_decoder = [
            (512, 2, 0.2),  # [batch, 2, 2, 1024] => [batch, 4, 4, 512]
            (256, 2, 0.2),  # [batch, 4, 4, 512] => [batch, 8, 8, 256]
            (128, 2, 0.2),  # [batch, 8, 8, 256] => [batch, 16, 16, 128]
            (64, 2, 0),     # [batch, 16, 16, 128] => [batch, 32, 32, 64]
            (64, 1, 0),     # [batch, 32, 32, 64] => [batch, 32, 32, 64]
        ]
        
        return Generator('gen', kernels_gen_encoder, kernels_gen_decoder)

    def create_discriminator(self):
        kernels_dis = [
            (64, 2, 0),     # [batch, 32, 32, ch] => [batch, 16, 16, 64]
            (128, 2, 0),    # [batch, 16, 16, 64] => [batch, 8, 8, 128]
            (256, 2, 0),    # [batch, 8, 8, 128] => [batch, 4, 4, 256]
            (512, 1, 0)     # [batch, 4, 4, 256] => [batch, 4, 4, 512]
        ]

        return Discriminator('dis', kernels_dis)

    def create_dataset(self, training=True):
        return Cifar10Dataset(
            path=self.options.dataset_path,
            training=training,
            augment=self.options.augment)


class Places365Model(BaseModel):
    def __init__(self, sess, options):
        super(Places365Model, self).__init__(sess, options)

    def get_input_shape(self):
        return (256, 256, 3)

    def create_generator(self):
        kernels_gen_encoder = [
            (64, 1, 0),     # [batch, 256, 256, ch] => [batch, 256, 256, 64]
            (64, 2, 0),     # [batch, 256, 256, 64] => [batch, 128, 128, 64]
            (128, 2, 0),    # [batch, 128, 128, 64] => [batch, 64, 64, 128]
            (256, 2, 0),    # [batch, 64, 64, 128] => [batch, 32, 32, 256]
            (512, 2, 0),    # [batch, 32, 32, 256] => [batch, 16, 16, 512]
            (512, 2, 0),    # [batch, 16, 16, 512] => [batch, 8, 8, 512]
            (512, 2, 0),    # [batch, 8, 8, 512] => [batch, 4, 4, 512]
            (512, 2, 0)     # [batch, 4, 4, 512] => [batch, 2, 2, 512]
        ]

        kernels_gen_decoder = [
            (512, 2, 0.2),  # [batch, 2, 2, 512] => [batch, 4, 4, 512]
            (512, 2, 0.2),  # [batch, 4, 4, 512] => [batch, 8, 8, 512]
            (512, 2, 0.2),  # [batch, 8, 8, 512] => [batch, 16, 16, 512]
            (256, 2, 0),    # [batch, 16, 16, 512] => [batch, 32, 32, 256]
            (128, 2, 0),    # [batch, 32, 32, 256] => [batch, 64, 64, 128]
            (64, 2, 0),     # [batch, 64, 64, 128] => [batch, 128, 128, 64]
            (64, 2, 0)      # [batch, 128, 128, 64] => [batch, 256, 256, 64]
        ]

        return Generator('gen', kernels_gen_encoder, kernels_gen_decoder)

    def create_discriminator(self):
        kernels_dis = [
            (64, 2, 0),     # [batch, 256, 256, ch] => [batch, 128, 128, 64]
            (128, 2, 0),    # [batch, 128, 128, 64] => [batch, 64, 64, 128]
            (256, 2, 0),    # [batch, 64, 64, 128] => [batch, 32, 32, 256]
            (512, 2, 0),    # [batch, 32, 32, 256] => [batch, 16, 16, 512]
            (512, 2, 0),    # [batch, 16, 16, 512] => [batch, 8, 8, 512]
            (512, 2, 0)     # [batch, 8, 8, 512] => [batch, 4, 4, 512]
        ]

        return Discriminator('dis', kernels_dis)

    def create_dataset(self, training=True):
        return Places365Dataset(
            path=self.options.dataset_path,
            training=training,
            augment=self.options.augment)


def model_factory(sess, options):
    if options.dataset == CIFAR10_DATASET:
        model = Cifar10Model(sess, options)

    elif options.dataset == PLACES365_DATASET:
        model = Places365Model(sess, options)

    if not os.path.exists(options.checkpoints_path):
        os.makedirs(options.checkpoints_path)

    if options.log:
        open(model.train_log_file, 'w').close()
        open(model.test_log_file, 'w').close()

    args = vars(options)
    print('\n------------ Options -------------')
    with open(os.path.join(options.checkpoints_path, 'options.dat'), 'w') as f:
        for k, v in sorted(args.items()):
            print('%s: %s' % (str(k), str(v)))
            f.write('%s: %s\n' % (str(k), str(v)))
    print('-------------- End ----------------\n')

    model.build()
    return model

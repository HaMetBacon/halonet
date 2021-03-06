#
# A keras implementation of a 3D CNN
#
# Authors: P. Berger, G. Stein
#
# References: 
# [1] V-Net https://arxiv.org/abs/1606.04797
# [2] V-Net in pytorch https://github.com/mattmacy/vnet.pytorch
# [3] Cosmology https://arxiv.org/pdf/1711.02033.pdf
# [4] YOLO (You Only Look Once)?
# 
#

#
# Things to check / add:
# - Dropout at fully connected layers
# - Average pooling vs. Max pooling
# - Batch normalization
# - Non-sequential (split and then collect)
# - Leaky ReLU
# - Strides in the convolution layers
#

import keras.models as km
import keras.layers as kl
from keras.layers.merge import add

import tensorflow as tf

#######################################################################


def get_model(nlevels, nfm = 16, input_shape = (64, 64, 64, 1), nconv=2, dropout_in=False, dropout_out=False, lrelu_alpha=None, batch_norm=False):

    """
    Returns a CNN V-Net Keras model.

    Parameters
    -----------
        nlevels: list
            Number of levels in the V-Net, which is the number of times the resolution of
            of the filter is halved.

        nfm: int 
            The number of feature maps in the first convolutional layer (default = 16).

        intput_shape: tuple, 
            the shape of the input data, 
            default = (64, 64, 64, 1)

    Output
    -------
        model: 
            the constructed Keras model.

    """

    #Define the PReLU activation
    #prelu = kl.advanced_activations.PReLU(init='uniform', weights=None)

    # Initialize the model.
    #This is not a Sequential model so create input state
    input_state = kl.Input(shape = input_shape)

    #These are hard coded following [1]
    conv_kernel_size = (5, 5, 5)
    updown_kernel_size = (2, 2, 2)
    updown_stride = updown_kernel_size

    def NonLinearity(t, lrelu=lrelu_alpha, dropout=False, batch_norm=batch_norm):
        if batch_norm:
            to = kl.BatchNormalization(scale=False)(t)
        else:
            to = t
        
        if lrelu is not None:
            to = kl.LeakyReLU(alpha=lrelu_alpha)(to)
        else:
            to = kl.PReLU()(to)

        if dropout:
            to = kl.Dropout(dropout)(to)
            
        return to

    # Fine grained features to forward
    forward_list = []

    for fi in range(nlevels):
        # Add the initial convolution layer, with nfm feature maps.
        # For simplicity we are doing two convolutions for each non-zero level (see [1]).
        if fi == 0:
            shortcut = input_state
            residual = kl.Conv3D(nfm, kernel_size = conv_kernel_size, padding='same')(input_state)
            residual = NonLinearity(residual, batch_norm=False)

        else:
            #shortcut = kl.Conv3D(nfm*2**fi, kernel_size = (1, 1, 1), padding='same')(x)
            shortcut = x
            residual = kl.Conv3D(nfm*2**fi, kernel_size = conv_kernel_size, padding='same')(x)
            residual = NonLinearity(residual, dropout=dropout_in, batch_norm=False)
            for ci in range(nconv-1):
                residual = kl.Conv3D(nfm*2**fi, kernel_size = conv_kernel_size, padding='same')(residual)
                residual = NonLinearity(residual, dropout=dropout_in,
                                        batch_norm=(ci==nconv-2) and batch_norm)

        # Perform elementwise sum with input to train on residuals.
        x = add([residual, shortcut])

        #Save a copy for fine-grained features forwarding
        forward_list.append(x)

        # Peform a down convolution with PReLU activation, double the number of feature maps.
        x = kl.Conv3D(nfm*2**(fi+1), kernel_size = updown_kernel_size, strides=updown_stride)(x)
        if abs(fi - nlevels) < nlevels:
            x = NonLinearity(x, dropout=dropout_out)
        else:
            x = NonLinearity(x)

        # Check average pooling vs. residual network?

    # Step back up to achieve initial resolution
    for fi in range(nlevels)[::-1]:

        #Grab the shortcut
        #shortcut = kl.Conv3D(nfm*2**(fi+1), kernel_size = (1, 1, 1), padding='same')(x)
        shortcut = x
        
        if fi != (nlevels-1):
            #Concatenate with fine grained forwarded features along filters axis
            x = kl.Concatenate(axis=-1)([forward_list[fi+1], x])
        
        # Do some convolutions, then forward the residuals
        residual = kl.Conv3D(nfm*2**(fi+1), kernel_size = conv_kernel_size, padding='same')(x)
        residual = NonLinearity(residual, dropout=dropout_in, batch_norm=False)
        for ci in range(nconv-1):
            residual = kl.Conv3D(nfm*2**(fi+1), kernel_size = conv_kernel_size, padding='same')(residual)
            residual = NonLinearity(residual, dropout=dropout_in,
                                    batch_norm=(ci==nconv-2) and batch_norm)
        x = add([residual, shortcut])

        # Peform a deconvolution with PReLU activation, halve the number of channels
        x = kl.Conv3DTranspose(nfm*2**fi, kernel_size = updown_kernel_size, strides=updown_stride)(x)
        if abs(fi - nlevels) < nlevels:
            x = NonLinearity(x, dropout=dropout_out)
        else:
            x = NonLinearity(x)

    # Data show should now have size (batch_size, input_x, input_y, input_z, nfm)
    # Final forwarding and convolution
    x = kl.Concatenate(axis=-1)([forward_list[0], x])
    residual = kl.Conv3D(nfm, kernel_size = conv_kernel_size, padding='same')(x)
    shortcut = kl.Conv3D(nfm, kernel_size = (1, 1, 1), padding='same')(x)
    x = add([residual, shortcut])
    x = NonLinearity(x, batch_norm=False)

    # Final layer is a (1, 1, 1) filter with 2 features corresponding to the
    # foreground and background (see [1]).
    x = kl.Conv3D(2, kernel_size = (1, 1, 1))(x)
    x = NonLinearity(x, batch_norm=False)

    # Apply softmax
    x = kl.Activation('softmax')(x)

    model = km.Model(inputs = input_state, outputs = x)

    return model

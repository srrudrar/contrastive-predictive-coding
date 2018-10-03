from data_utils import SortedNumberGenerator
from os.path import join, basename, dirname, exists
import keras
from keras import backend as K

# what is our code_size? what should be our filter sizes?
def network_encoder(x, code_size):
    x = keras.layers.Conv1D(filters=(code_size)/7, kernel_size=10, strides=5, activation='linear')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.LeakyReLU()(x)
    x = keras.layers.Conv1D(filters=(code_size)/49, kernel_size=8, strides=4, activation='linear')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.LeakyReLU()(x)
    x = keras.layers.Conv1D(filters=(code_size)/147, kernel_size=4, strides=2, activation='linear')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.LeakyReLU()(x)
    x = keras.layers.Conv1D(filters=(code_size)/441, kernel_size=4, strides=2, activation='linear')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.LeakyReLU()(x)
    x = keras.layers.Conv1D(filters=(code_size)/441, kernel_size=4, strides=2, activation='linear')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.LeakyReLU()(x)
    x = keras.layers.Flatten()(x)
    x = keras.layers.Dense(units=512, activation='linear')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.ReLU()(x)
    x = keras.layers.Dense(units=code_size, activation='linear', name='encoder_embedding')(x)
    return x


def network_autoregressive(x):
    # x = keras.layers.GRU(units=256, return_sequences=True)(x)
    # x = keras.layers.BatchNormalization()(x)
    x = keras.layers.GRU(units=256, return_sequences=False, name='ar_context')(x)
    return x


# from context c, predict 12 timesteps in the future. predict_terms = 12
def network_prediction(context, code_size, predict_terms):
    outputs = []
    for i in range(predict_terms):
        outputs.append(keras.layers.Dense(units=code_size, activation="linear", name='z_t_{i}'.format(i=i))(context))

    if len(outputs) == 1:
        output = keras.layers.Lambda(lambda x: K.expand_dims(x, axis=1))(outputs[0])
    else:
        output = keras.layers.Lambda(lambda x: K.stack(x, axis=1))(outputs)
    return output


# Contrastive loss layer. Dot product of predictions and true value.
class CPCLayer(keras.layers.Layer):
    def __init__(self, **kwargs):
        super(CPCLayer, self).__init__(**kwargs)

    def call(self, inputs):
        # Compute dot product among vectors
        preds, y_encoded = inputs
        dot_product = K.mean(y_encoded * preds, axis=-1)
        dot_product = K.mean(dot_product, axis=-1, keepdims=True)  # average along the temporal dimension
        # Keras loss functions take probabilities
        dot_product_probs = K.sigmoid(dot_product)
        return dot_product_probs

    def compute_output_shape(self, input_shape):
        return (input_shape[0][0], 1)


# Network model combining genc and gar
def network_cpc(image_shape, terms, predict_terms, code_size, learning_rate):


    # Set learning phase (https://stackoverflow.com/questions/42969779/keras-error-you-must-feed-a-value-for-placeholder-tensor-bidirectional-1-keras)
    K.set_learning_phase(1)

    # Define encoder model
    encoder_input = keras.layers.Input(image_shape)
    encoder_output = network_encoder(encoder_input, code_size)
    encoder_model = keras.models.Model(encoder_input, encoder_output, name='encoder')
    encoder_model.summary()

    # Define rest of model
    x_input = keras.layers.Input((terms, image_shape[0], image_shape[1], image_shape[2]))
    x_encoded = keras.layers.TimeDistributed(encoder_model)(x_input)
    context = network_autoregressive(x_encoded)
    preds = network_prediction(context, code_size, predict_terms)

    y_input = keras.layers.Input((predict_terms, image_shape[0], image_shape[1], image_shape[2]))
    y_encoded = keras.layers.TimeDistributed(encoder_model)(y_input)

    # Loss
    dot_product_probs = CPCLayer()([preds, y_encoded])

    # Model
    cpc_model = keras.models.Model(inputs=[x_input, y_input], outputs=dot_product_probs)

    # Compile model
    cpc_model.compile(
        optimizer=keras.optimizers.Adam(lr=learning_rate),
        loss='binary_crossentropy',
        metrics=['binary_accuracy']
    )
    cpc_model.summary()

    return cpc_model



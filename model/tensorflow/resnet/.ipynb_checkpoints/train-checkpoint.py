import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import preprocessing

from model import resnet_50

if __name__ == '__main__':
    trn_data_dir = 'dataset/casting_data/train'
    val_data_dir = 'dataset/casting_data/test'
    batch_size = 64
    img_height = 224
    img_width = 224
    epochs = 20
    
    model = resnet_50(num_classes=1)
    model.build(input_shape=(None, img_height, img_width, 3))
    
    train_ds = tf.keras.preprocessing.image_dataset_from_directory(
        trn_data_dir,
        # validation_split=0.2,
        label_mode = 'binary',
        # subset="training",
        seed=123,
        shuffle=True,
        image_size=(img_height, img_width),
        batch_size=batch_size
    )

    val_ds = tf.keras.preprocessing.image_dataset_from_directory(
        val_data_dir,
        # validation_split=0.2,
        label_mode = 'binary',
        # subset="validation",
        shuffle=False,
        seed=123,
        image_size=(img_height, img_width),
        batch_size=batch_size
    )
    
    data_augmentation = keras.Sequential(
      [
        keras.layers.experimental.preprocessing.Rescaling(1./255),
        keras.layers.experimental.preprocessing.Normalization(mean=[0.485, 0.456, 0.406], variance=[0.229, 0.224, 0.225]),
        keras.layers.experimental.preprocessing.RandomFlip("horizontal", input_shape=(img_height, img_width, 3)),
        keras.layers.experimental.preprocessing.RandomFlip("vertical",   input_shape=(img_height, img_width, 3)),
      ]
    )

    val_processing = keras.Sequential(
      [
        keras.layers.experimental.preprocessing.Rescaling(1./255),
        keras.layers.experimental.preprocessing.Normalization(mean=[0.485, 0.456, 0.406], variance=[0.229, 0.224, 0.225])
      ]
    )

    trn_ds = train_ds.map(lambda x, y: (data_augmentation(x), y))
    val_ds = val_ds.map(lambda x, y: (val_processing(x), y))
    
    
    # gen, total = create_batch_generator('dataset/casting_data/test')
            
    criterion = tf.keras.losses.BinaryCrossentropy()
    optimizer = tf.keras.optimizers.Adam()
    
    train_loss = tf.keras.metrics.Mean(name='train_loss')
    train_accuracy = tf.keras.metrics.BinaryAccuracy(name='train_accuracy')

    valid_loss = tf.keras.metrics.Mean(name='valid_loss')
    valid_accuracy = tf.keras.metrics.BinaryAccuracy(name='valid_accuracy')
    
    @tf.function
    def train_step(model, images, labels, criterion, optimizer):
        with tf.GradientTape() as tape:
            predictions = model(images, training=True)
            loss = criterion(y_true=labels, y_pred=predictions)
            gradients = tape.gradient(loss, model.trainable_variables)
            optimizer.apply_gradients(grads_and_vars=zip(gradients, model.trainable_variables))

        train_loss(loss)
        train_accuracy(labels, predictions)
        

    @tf.function
    def valid_step(model, images, labels, criterion):
        predictions = model(images, training=False)
        v_loss = criterion(labels, predictions)

        valid_loss(v_loss)
        valid_accuracy(labels, predictions)
    
    
    best_loss = 999999.9
    # start training
    for epoch in range(epochs):
        train_loss.reset_states()
        train_accuracy.reset_states()
        valid_loss.reset_states()
        valid_accuracy.reset_states()
        for images, labels in trn_ds:
            train_step(model, images, labels, criterion, optimizer)
            
        print("Trn - Epoch: {}/{}, loss: {:.5f}, accuracy: {:.5f}".format(epoch + 1,
                                                                     epochs,
                                                                     train_loss.result(),
                                                                     train_accuracy.result()))
            
        for images, labels in val_ds:
            valid_step(model, images, labels, criterion)
            
        print("Val - Epoch: {}/{}, loss: {:.5f}, accuracy: {:.5f}".format(epoch + 1,
                                                                     epochs,
                                                                     valid_loss.result(),
                                                                     valid_accuracy.result()))
        
        if (best_loss > valid_loss.result()):
            best_loss = valid_loss.result()
            model.save_weights('check_points/resnet50/model_lite.h5')
            print('best loss! model saved.')
   
# store data in an encrypted file using the AES algorithm

import cryptolib
import machine

BLOCK_SIZE = 16

# pad machine unique ID so that is is a suitable key length for AES
unique_id = machine.unique_id()
if len(unique_id) < 32:
    unique_id = machine.unique_id() + b'\x00' * (16 - len(machine.unique_id()))

def store_encrypted_file(filename, data):
    """
    Store data in an encrypted file using the AES algorithm.
    
    :param filename: The name of the file to store the encrypted data.
    :param data: The data to be encrypted and stored.
    """
    
    aes = cryptolib.aes(unique_id, 1)  # Initialize the AES encryption object

    pad = BLOCK_SIZE - len(data) % BLOCK_SIZE
    plaintext = data + " " * pad  # Pad the data to be a multiple of BLOCK_SIZE
    # Encrypt the data
    encrypted_data = aes.encrypt(plaintext)
    
    # Write the encrypted data to the file
    with open(filename, 'wb') as file:
        file.write(encrypted_data)

def read_encrypted_file(filename):
    """
    Read data from an encrypted file and decrypt it.
    
    :param filename: The name of the file to read the encrypted data from.
    :return: The decrypted data.
    """
    aes = cryptolib.aes(unique_id, 1)  # Initialize the AES decryption object
    
    # Read the encrypted data from the file
    with open(filename, 'rb') as file:
        encrypted_data = file.read()
    
    # Decrypt the data
    decrypted_data = aes.decrypt(encrypted_data)
    
    return decrypted_data
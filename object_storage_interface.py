from abc import ABC, abstractmethod

class ObjectStorageInterface(ABC):
    @abstractmethod
    def get_versioning_configuration(self, bucket_name):

    @abstractmethod
    def update_versioning_configuration(self, bucket_name, status)
  

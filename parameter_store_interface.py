from abc import ABC, abstractmethod

class ParameterStoreInterface(ABC):
    @abstractmethod
    def get_parameter(self, name):

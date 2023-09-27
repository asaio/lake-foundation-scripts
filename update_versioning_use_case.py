class UpdateVersioningUseCase:
    def __init__(self, object_storage_adapter, parameter_store_adapter, versioning_history):
        self.object_storage_adapter = object_storage_adapter
        self.parameter_store_adapter = parameter_store_adapter
        self.versioning_history = versioning_history

    def _validate_update_is_required(self, bucket_name):
        # Get the current versioning configuration from the object storage adapter
        current_versioning = self.object_storage_adapter.get_versioning_configuration(bucket_name)

        # Get the expected versioning configuration from the parameter store
        expected_versioning = self.parameter_store_adapter.get_parameter("/tag/name")

        self.versioning_history.before = current_versioning
        self.versioning_history.after = None
        self.versioning_history.expected = expected_versioning
        # Compare the current and expected versioning configurations
        if current_versioning != expected_versioning:
            # Return True to indicate that an update is required
            return True

        # Return False if no update is required
        return False

    def assure_versioning_configuration(self):
        update_required = _validate_update_is_required('my')
        if update_required:
            self.object_storage_adapter.update_versioning_configuration(bucket_name, self.versioning_history.expected)
            current_versioning = self.object_storage_adapter.get_versioning_configuratiom(bucket_namd)
            if current_versioning == self.versioning_history.expected:
                self.versioning_history.after = self.versioning_history.expected
                return True, self.versioning_history
            else:
              return False, self.versioning_history

        return True, self.versioning_history
      

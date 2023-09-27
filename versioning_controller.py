class VersioningController:
    def __init__(self, s3_adapter, ssm_adapter, versioning_history):
        # Instantiate the UpdateVersioningUseCase with the dependencies
        self.update_versioning_use_case = UpdateVersioningUseCase(s3_adapter, ssm_adapter, versioning_history)

    def validate_event(self, event):
        # Check if the event contains "/tag/name"
        return "/tag/name" in event

    def process_event(self, bucket_name):
        # Check if an update is required and get the updated versioning configuration
        update_required, updated_versioning = self.update_versioning_use_case.assure_versioning_configuration(bucket_name)

        if update_required:
            # Log or perform any necessary actions based on the update
            print(f"Versioning configuration updated to: {updated_versioning}")
        else:
            print("No versioning configuration update needed")

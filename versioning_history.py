class VersioningHistory:
    def __init__(self):
        self._before = None
        self._after = None
        self._expected = None

    @property
    def before(self):
        return self._before

    @before.setter
    def before(self, value):
        self._validate_versioning_status(value)
        self._before = value

    @property
    def after(self):
        return self._after

    @after.setter
    def after(self, value):
        self._validate_versioning_status(value)
        self._after = value

    @property
    def expected(self):
        return self._expected

    @expected.setter
    def expected(self, value):
        self._validate_versioning_status(value)
        self._expected = value

    def _validate_versioning_status(self, value):
        if value is not None and value not in ["Suspended", "Enabled"]:
          raise ValueError("Versioning status must be 'Suspended' or 'Enabled'")
  

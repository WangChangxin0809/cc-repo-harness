"""Uniform classified failures across the copied runtime."""


class MemoryFailure(Exception):
    def __init__(self, status, message, details=None):
        super().__init__(message)
        self.status = status
        self.details = details or {}
        self.code = 2 if status in ('unsupported', 'unjudged') else 1

    def receipt(self):
        return {'status': self.status, 'code': self.code, 'message': str(self),
                'details': self.details}

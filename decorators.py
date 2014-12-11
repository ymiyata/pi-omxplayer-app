def playing(func):
    """Decorator to ensure function only gets executed if there is
    video playing.
    """
    def wrapper(self, *args, **params):
        if self.is_playing():
            func(self, *args, **params)
    return wrapper

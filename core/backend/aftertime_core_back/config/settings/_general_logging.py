LOGLEVEL = 'DEBUG'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            # exact format is not important, this is the minimum information
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        },
    },
    'handlers': {
        # console logs to stderr
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': './log/general.log',
            'formatter': 'default',
        },
    },
    'loggers': {
        # default for all undefined Python modules
        '': {
            'level': LOGLEVEL,
            'handlers': ['console', 'file'],
        },
    },
   }

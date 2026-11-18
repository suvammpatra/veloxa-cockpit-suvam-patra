import logging
import logging.config


def setup_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {"format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s"}
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "plain"}
            },
            "root": {"level": level.upper(), "handlers": ["console"]},
        }
    )
    logging.getLogger(__name__).debug("Logging configured at %s", level)

import logging

from evidenceops.logging import configure_logging, get_logger


def test_logging_factory_and_basic_configuration(caplog) -> None:
    configure_logging("INFO")
    logger = get_logger("evidenceops.test")
    with caplog.at_level(logging.INFO, logger="evidenceops.test"):
        logger.info("domain contract initialized")
    assert logger.name == "evidenceops.test"
    assert "domain contract initialized" in caplog.text

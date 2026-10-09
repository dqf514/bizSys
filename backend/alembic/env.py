from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.db import Base

# 导入全部含表模型，保证 autogenerate 可见
from app.modules.admin import models as admin_models  # noqa: F401
from app.modules.approval import models as approval_models  # noqa: F401
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.contract import models as contract_models  # noqa: F401
from app.modules.crm import models as crm_models  # noqa: F401
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.settings import models as settings_models  # noqa: F401
from app.modules.task import models as task_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

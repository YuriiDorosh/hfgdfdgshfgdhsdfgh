# app/odoo_client.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import odoorpc


@dataclass
class OdooConfig:
    host: str
    port: int
    db: str
    user: str
    password: str
    protocol: str = "jsonrpc"


def load_odoo_config(prefix: str) -> OdooConfig:
    return OdooConfig(
        host=os.getenv(f"{prefix}_HOST", "localhost"),
        port=int(os.getenv(f"{prefix}_PORT", "8069")),
        db=os.getenv(f"{prefix}_DB", "odoo"),
        user=os.getenv(f"{prefix}_USER", "admin"),
        password=os.getenv(f"{prefix}_PASSWORD", "admin"),
        protocol=os.getenv(f"{prefix}_PROTOCOL", "jsonrpc"),
    )


class OdooClient:
    def __init__(self, cfg: OdooConfig) -> None:
        self.cfg = cfg
        self._client: Optional[odoorpc.ODOO] = None

    def connect(self) -> odoorpc.ODOO:
        if self._client is None:
            self._client = odoorpc.ODOO(
                self.cfg.host,
                port=self.cfg.port,
                protocol=self.cfg.protocol,
            )
            self._client.login(self.cfg.db, self.cfg.user, self.cfg.password)
        return self._client

    @property
    def env(self):
        """
        Shortcut для self.connect().env — як env в самому Odoo.
        """
        return self.connect().env


# Odoo 1 == "джерело"
odoo1_client = OdooClient(load_odoo_config("ODOO_1"))
# Odoo 2 == "ціль / дзеркало"
odoo2_client = OdooClient(load_odoo_config("ODOO_2"))

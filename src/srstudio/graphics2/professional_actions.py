from __future__ import annotations

"""Small stable façade for professional G2 flyer editor actions.

Qt/QML and the Command Router should not need to know which domain service owns
an operation. Keeping this façade thin lets UI wiring evolve without coupling
QML to ProductCard, PriceBlock, image and page implementation details.
"""

from dataclasses import dataclass
from typing import Any

from .asset_edit import replace_image
from .operations import GraphicsSession
from .page_management import delete_page, duplicate_page, rename_page, reorder_page
from .price_edit import edit_price_block
from .product_card_edit import edit_product_card
from .text_edit import update_text_style
from .usability_gate import G2UsabilityReport, inspect_g2_usability


@dataclass(slots=True)
class G2ProfessionalActions:
    session: GraphicsSession

    def duplicate_page(self, page_id: str | None = None, *, name: str | None = None) -> str:
        return duplicate_page(self.session, page_id, name=name)

    def rename_page(self, page_id: str, name: str) -> bool:
        return rename_page(self.session, page_id, name)

    def delete_page(self, page_id: str) -> bool:
        return delete_page(self.session, page_id)

    def reorder_page(self, page_id: str, target_index: int) -> bool:
        return reorder_page(self.session, page_id, target_index)

    def replace_image(self, node_id: str, source: str, *, reset_framing: bool = False) -> bool:
        return replace_image(self.session, node_id, source, reset_framing=reset_framing)

    def edit_text_style(self, node_id: str, **style: Any) -> bool:
        return update_text_style(self.session, node_id, **style)

    def edit_price_block(
        self,
        block_id: str,
        price: object,
        *,
        unit: object | None = None,
        currency: str = "R$",
    ) -> bool:
        return edit_price_block(self.session, block_id, price, unit=unit, currency=currency)

    def edit_product_card(
        self,
        slot_id: str,
        *,
        name: str | None = None,
        price: object | None = None,
        unit: object | None = None,
        image_source: str | None = None,
        limit: str | None = None,
        app_price: object | None = None,
    ) -> bool:
        return edit_product_card(
            self.session,
            slot_id,
            name=name,
            price=price,
            unit=unit,
            image_source=image_source,
            limit=limit,
            app_price=app_price,
        )

    def inspect_usability(self, *, require_multi_product_page: bool = False) -> G2UsabilityReport:
        return inspect_g2_usability(
            self.session.document,
            require_multi_product_page=require_multi_product_page,
        )

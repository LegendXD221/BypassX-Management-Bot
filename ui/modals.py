"""Shared Discord modal builders for BypassX interactions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import discord


SubmitCallback = Callable[[discord.Interaction, dict[str, str]], Awaitable[None]]


class FormModal(discord.ui.Modal):
    """Generic modal that collects one or more text inputs."""

    def __init__(
        self,
        *,
        title: str,
        fields: tuple[tuple[str, str, str, bool], ...],
        on_submit_callback: SubmitCallback | None = None,
    ) -> None:
        super().__init__(title=title[:45], timeout=300)
        self._on_submit_callback = on_submit_callback
        self._fields: dict[str, discord.ui.TextInput] = {}
        for custom_id, label, placeholder, required in fields:
            field = discord.ui.TextInput(
                custom_id=custom_id,
                label=label[:45],
                placeholder=placeholder[:100],
                required=required,
                max_length=4000,
            )
            self._fields[custom_id] = field
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {custom_id: str(field.value) for custom_id, field in self._fields.items()}
        if self._on_submit_callback is not None:
            await self._on_submit_callback(interaction, values)


class ReasonModal(FormModal):
    """Standard required moderation reason modal."""

    def __init__(self, on_submit_callback: SubmitCallback | None = None) -> None:
        super().__init__(
            title="Moderation Reason",
            fields=(
                (
                    "reason",
                    "Reason",
                    "Enter the reason for this action.",
                    True,
                ),
            ),
            on_submit_callback=on_submit_callback,
        )


class ConfirmationModal(FormModal):
    """Confirmation modal requiring the user to type a specified phrase."""

    def __init__(
        self,
        phrase: str,
        on_submit_callback: SubmitCallback | None = None,
    ) -> None:
        self.phrase = phrase
        super().__init__(
            title="Confirm Action",
            fields=(
                (
                    "confirmation",
                    f"Type {phrase}",
                    f"Type {phrase} to continue.",
                    True,
                ),
            ),
            on_submit_callback=self._validate_and_submit(on_submit_callback),
        )

    def _validate_and_submit(self, callback: SubmitCallback | None) -> SubmitCallback:
        async def handler(interaction: discord.Interaction, values: dict[str, str]) -> None:
            if values.get("confirmation", "").strip() != self.phrase:
                from ui.containers import error

                await interaction.response.send_message(
                    **error("Confirmation phrase did not match."),
                    ephemeral=True,
                )
                return
            if callback is not None:
                await callback(interaction, values)

        return handler


def reason_modal(on_submit: SubmitCallback | None = None) -> ReasonModal:
    """Return a standard reason modal instance."""
    return ReasonModal(on_submit)


def confirmation_modal(
    phrase: str,
    on_submit: SubmitCallback | None = None,
) -> ConfirmationModal:
    """Return a phrase-confirmation modal instance."""
    return ConfirmationModal(phrase, on_submit)


def text_modal(
    title: str,
    custom_id: str,
    label: str,
    placeholder: str = "",
    *,
    required: bool = True,
    on_submit: SubmitCallback | None = None,
) -> FormModal:
    """Return a generic one-field text modal."""
    return FormModal(
        title=title,
        fields=((custom_id, label, placeholder, required),),
        on_submit_callback=on_submit,
    )


__all__ = [
    "ConfirmationModal",
    "FormModal",
    "ReasonModal",
    "confirmation_modal",
    "reason_modal",
    "text_modal",
]

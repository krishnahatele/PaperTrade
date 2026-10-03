"""The private Telegram control bot: token, linking, notification preferences."""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep
from app.services.bot import BotStatus
from app.services.runtime import BotNotify, BotRuntime

router = APIRouter(prefix="/bot", tags=["telegram bot"])


class TokenBody(BaseModel):
    token: str = Field(min_length=20, max_length=200, description="From @BotFather")


class LinkInfo(BaseModel):
    code: str
    url: str


@router.get("", response_model=BotStatus)
async def bot_status(container: ContainerDep) -> BotStatus:
    return await container.bot.status()


@router.put("/token", response_model=BotStatus, summary="Save a bot token from @BotFather")
async def save_token(body: TokenBody, container: ContainerDep) -> BotStatus:
    return await container.bot.save_token(body.token)


@router.delete("/token", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(container: ContainerDep) -> None:
    await container.bot.clear()


@router.post(
    "/create",
    response_model=BotStatus,
    summary="Create the bot via @BotFather with your Telegram login and link it automatically",
)
async def create_bot(container: ContainerDep) -> BotStatus:
    return await container.bot.create_with_botfather()


@router.post("/link", response_model=LinkInfo, summary="One-time link: open it and press Start")
async def link(container: ContainerDep) -> dict[str, str]:
    return await container.bot.link_code()


@router.post("/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink(container: ContainerDep) -> None:
    await container.runtime.update(BotRuntime, owner_chat_id=None, owner_name=None)


@router.post("/test", status_code=status.HTTP_204_NO_CONTENT)
async def test_message(container: ContainerDep) -> None:
    await container.bot.send_test()


@router.patch("/notify", response_model=BotStatus)
async def set_notify(body: BotNotify, container: ContainerDep) -> BotStatus:
    await container.runtime.update(BotRuntime, notify=body.model_dump())
    return await container.bot.status()

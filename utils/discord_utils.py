import discord
from discord.ext import commands
from typing import Optional, List


# =============================================================================
# Discord Utilities
# =============================================================================
# A collection of utility functions for validating, fetching, creating, and
# deleting Discord guild resources such as channels, roles, and categories.


def get_text_channel(bot: commands.Bot, channel_id: int) -> Optional[discord.TextChannel]:
    """
    Retrieve a TextChannel by ID from the bot's cache.

    Parameters:
        bot: The commands.Bot instance.
        channel_id: The ID of the text channel to retrieve.

    Returns:
        The TextChannel if found, otherwise None.
    """
    channel = bot.get_channel(channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


def validate_text_channel(bot: commands.Bot, channel_id: int) -> bool:
    """
    Check whether a given ID corresponds to a valid TextChannel the bot can see.

    Parameters:
        bot: The commands.Bot instance.
        channel_id: The ID to validate.

    Returns:
        True if the channel exists and is a TextChannel, False otherwise.
    """
    return get_text_channel(bot, channel_id) is not None


def get_category(guild: discord.Guild, category_id: int) -> Optional[discord.CategoryChannel]:
    """
    Retrieve a CategoryChannel by ID from a guild.

    Parameters:
        guild: The Guild instance.
        category_id: The ID of the category to retrieve.

    Returns:
        The CategoryChannel if found, otherwise None.
    """
    channel = guild.get_channel(category_id)
    return channel if isinstance(channel, discord.CategoryChannel) else None


def validate_category(guild: discord.Guild, category_id: int) -> bool:
    """
    Check whether a given ID corresponds to a valid CategoryChannel in the guild.

    Parameters:
        guild: The Guild instance.
        category_id: The ID to validate.

    Returns:
        True if the category exists and is a CategoryChannel, False otherwise.
    """
    return get_category(guild, category_id) is not None


def get_role(guild: discord.Guild, role_id: int) -> Optional[discord.Role]:
    """
    Retrieve a Role by ID from a guild.

    Parameters:
        guild: The Guild instance.
        role_id: The ID of the role to retrieve.

    Returns:
        The Role if found, otherwise None.
    """
    return guild.get_role(role_id)


def validate_role(guild: discord.Guild, role_id: int) -> bool:
    """
    Check whether a given ID corresponds to a valid Role in the guild.

    Parameters:
        guild: The Guild instance.
        role_id: The ID to validate.

    Returns:
        True if the role exists, False otherwise.
    """
    return get_role(guild, role_id) is not None


async def ensure_category(guild: discord.Guild, name: str, 
                          overwrites: Optional[dict] = None,
                          position: Optional[int] = None) -> discord.CategoryChannel:
    """
    Ensure a category with the given name exists in the guild. Create it if missing.

    Parameters:
        guild: The Guild instance.
        name:   The name of the category.
        overwrites: Optional permissions overwrites dict (role or member -> Permissions).
        position: Optional position index in the category list.

    Returns:
        The existing or newly created CategoryChannel.
    """
    existing = discord.utils.get(guild.categories, name=name)
    if existing:
        return existing
    return await guild.create_category(
        name=name,
        overwrites=overwrites or {},
        position=position
    )


async def ensure_text_channel(guild: discord.Guild, name: str,
                              category: Optional[discord.CategoryChannel] = None,
                              overwrites: Optional[dict] = None,
                              position: Optional[int] = None) -> discord.TextChannel:
    """
    Ensure a text channel with the given name exists. Create if missing, optionally under a category.

    Parameters:
        guild: The Guild instance.
        name:   The desired channel name.
        category: Optional CategoryChannel to place the channel under.
        overwrites: Optional permissions overwrites dict.
        position: Optional position within category.

    Returns:
        The existing or newly created TextChannel.
    """
    existing = discord.utils.get(guild.text_channels, name=name)
    if existing:
        return existing
    return await guild.create_text_channel(
        name=name,
        category=category,
        overwrites=overwrites or {},
        position=position
    )

async def ensure_role(guild: discord.Guild, name: str, 
                      permissions: Optional[discord.Permissions] = None,
                      colour: Optional[discord.Colour] = None,
                      hoist: bool = False) -> discord.Role:
    """
    Ensure a role with the given name exists in the guild. Create it if missing.

    Parameters:
        guild: The Guild instance.
        name:  The desired role name.
        permissions: Optional Permissions to assign.
        colour: Optional Colour for the role.
        hoist: Whether the role should be displayed separately.

    Returns:
        The existing or newly created Role.
    """
    existing = discord.utils.get(guild.roles, name=name)
    if existing:
        return existing
    return await guild.create_role(
        name=name,
        permissions=permissions or discord.Permissions.none(),
        colour=colour or discord.Colour.default(),
        hoist=hoist
    )

async def delete_channel(channel: discord.abc.GuildChannel) -> None:
    """
    Delete a channel (text, voice, or category) from the guild.

    Parameters:
        channel: The GuildChannel to delete.
    """
    await channel.delete()

async def delete_role(role: discord.Role) -> None:
    """
    Delete a role from the guild.

    Parameters:
        role: The Role to delete.
    """
    await role.delete()
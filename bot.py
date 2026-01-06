import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
import datetime
import json
import os
import csv
import io
import shortuuid
from typing import Optional, List, Union
from pathlib import Path

# Bot with necessary intents
intents = discord.Intents.default()
intents.messages = True
intents.reactions = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


DATA_PATH = os.getenv('DATA_PATH', '/data')
Path(DATA_PATH).mkdir(parents=True, exist_ok=True)

# Files for data storage with absolute paths
GIVEAWAY_FILE = os.path.join(DATA_PATH, "giveaways.json")
SERVER_SETTINGS_FILE = os.path.join(DATA_PATH, "server_settings.json")
STATISTICS_FILE = os.path.join(DATA_PATH, "statistics.json")
ENDED_GIVEAWAYS_FILE = os.path.join(DATA_PATH, "ended_giveaways.json")

# Log file paths
logger.info(f"Data directory: {DATA_PATH}")
logger.info(f"Giveaway file: {GIVEAWAY_FILE}")
logger.info(f"Settings file: {SERVER_SETTINGS_FILE}")

# Dictionaries for data storage
active_giveaways = {}
server_settings = {}
user_statistics = {}
ended_giveaways = {}  # Neues Dictionary für beendete Giveaways


def generate_giveaway_id():
    """Generate a short, unique ID for giveaways"""
    return shortuuid.ShortUUID().random(length=8).upper()


class GiveawayEditView(discord.ui.View):
    """View for editing giveaways"""
    def __init__(self, giveaway_id: str, interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.giveaway_id = giveaway_id
        self.interaction = interaction
        self.giveaway_data = active_giveaways.get(giveaway_id)
        
    @discord.ui.select(
        placeholder="Choose what to edit...",
        options=[
            discord.SelectOption(label="Edit Prize", value="prize", emoji="🎁"),
            discord.SelectOption(label="Edit Winners Count", value="winners", emoji="🏆"),
            discord.SelectOption(label="Edit Duration", value="duration", emoji="⏰"),
            discord.SelectOption(label="Edit Description", value="description", emoji="📝"),
            discord.SelectOption(label="Edit Allowed Roles", value="roles", emoji="👥"),
            discord.SelectOption(label="Edit Winner Role", value="winner_role", emoji="👑"),
            discord.SelectOption(label="Edit DM Message", value="dm", emoji="✉️"),
            discord.SelectOption(label="Cancel Giveaway", value="cancel", emoji="❌"),
            discord.SelectOption(label="End Giveaway Now", value="end_now", emoji="🚀"),
        ]
    )
    async def edit_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle selection from edit menu"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions to edit giveaways!", ephemeral=True)
            return
        
        if not self.giveaway_data:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        selected = select.values[0]
        
        if selected == "prize":
            await self.edit_prize(interaction)
        elif selected == "winners":
            await self.edit_winners(interaction)
        elif selected == "duration":
            await self.edit_duration(interaction)
        elif selected == "description":
            await self.edit_description(interaction)
        elif selected == "roles":
            await self.edit_roles(interaction)
        elif selected == "winner_role":
            await self.edit_winner_role(interaction)
        elif selected == "dm":
            await self.edit_dm_message(interaction)
        elif selected == "cancel":
            await self.cancel_giveaway(interaction)
        elif selected == "end_now":
            await self.end_giveaway_now(interaction)
    
    async def edit_prize(self, interaction: discord.Interaction):
        """Open modal to edit prize"""
        modal = PrizeEditModal(self.giveaway_id, self.giveaway_data['prize'])
        await interaction.response.send_modal(modal)
    
    async def edit_winners(self, interaction: discord.Interaction):
        """Open modal to edit winners count"""
        modal = WinnersEditModal(self.giveaway_id, self.giveaway_data['winners_count'])
        await interaction.response.send_modal(modal)
    
    async def edit_duration(self, interaction: discord.Interaction):
        """Open modal to edit duration"""
        modal = DurationEditModal(self.giveaway_id)
        await interaction.response.send_modal(modal)
    
    async def edit_description(self, interaction: discord.Interaction):
        """Open modal to edit description"""
        try:
            channel = bot.get_channel(self.giveaway_data['channel_id'])
            message = await channel.fetch_message(self.giveaway_data['message_id'])
            embed = message.embeds[0]
            current_description = None
            for field in embed.fields:
                if field.name == "Description":
                    current_description = field.value
                    break
        except:
            current_description = None
        
        modal = DescriptionEditModal(self.giveaway_id, current_description)
        await interaction.response.send_modal(modal)
    
    async def edit_roles(self, interaction: discord.Interaction):
        """Open modal to edit allowed roles"""
        allowed_roles = self.giveaway_data.get('allowed_roles', [])
        roles_text = ""
        if allowed_roles:
            roles_text = " ".join([f"<@&{role_id}>" for role_id in allowed_roles])
        
        modal = RolesEditModal(self.giveaway_id, roles_text)
        await interaction.response.send_modal(modal)
    
    async def edit_winner_role(self, interaction: discord.Interaction):
        """Open modal to edit winner role"""
        winner_role_id = self.giveaway_data.get('winner_role')
        role_text = f"<@&{winner_role_id}>" if winner_role_id else ""
        
        modal = WinnerRoleEditModal(self.giveaway_id, role_text)
        await interaction.response.send_modal(modal)
    
    async def edit_dm_message(self, interaction: discord.Interaction):
        """Open modal to edit DM message"""
        dm_message = self.giveaway_data.get('dm_message', "")
        
        modal = DMMessageEditModal(self.giveaway_id, dm_message)
        await interaction.response.send_modal(modal)
    
    async def cancel_giveaway(self, interaction: discord.Interaction):
        """Cancel the giveaway"""
        from discord.app_commands import CommandInteraction
        cmd_interaction = CommandInteraction(data={"id": "1"}, state=interaction._state)
        cmd_interaction._state = interaction._state
        cmd_interaction.user = interaction.user
        cmd_interaction.guild = interaction.guild
        
        await giveaway_cancel(cmd_interaction, self.giveaway_id)
        await interaction.response.send_message("✅ Giveaway cancellation initiated!", ephemeral=True)
    
    async def end_giveaway_now(self, interaction: discord.Interaction):
        """End giveaway immediately"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permissions!", ephemeral=True)
            return
        
        await end_giveaway(self.giveaway_id, 0)
        await interaction.response.send_message(f"✅ Giveaway **{self.giveaway_data['prize']}** is ending now!", ephemeral=True)


# Modals for editing (unchanged)
class PrizeEditModal(discord.ui.Modal, title="Edit Giveaway Prize"):
    def __init__(self, giveaway_id: str, current_prize: str):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.prize = discord.ui.TextInput(
            label="New Prize",
            placeholder="Enter the new prize...",
            default=current_prize,
            style=discord.TextStyle.short,
            max_length=200
        )
        self.add_item(self.prize)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle prize update"""
        if self.giveaway_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        active_giveaways[self.giveaway_id]['prize'] = self.prize.value
        
        try:
            channel = bot.get_channel(active_giveaways[self.giveaway_id]['channel_id'])
            message = await channel.fetch_message(active_giveaways[self.giveaway_id]['message_id'])
            embed = message.embeds[0]
            
            for i, field in enumerate(embed.fields):
                if field.name == "Prize":
                    embed.set_field_at(i, name="Prize", value=f"**{self.prize.value}**", inline=True)
                    break
            
            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating prize: {e}")
        
        save_giveaways()
        
        await interaction.response.send_message(f"✅ Prize updated to: **{self.prize.value}**", ephemeral=True)
        await log_to_audit_channel(interaction.guild.id,
                                 f"✏️ {interaction.user.mention} updated prize to **{self.prize.value}** for giveaway ID: {self.giveaway_id}")


class WinnersEditModal(discord.ui.Modal, title="Edit Winners Count"):
    def __init__(self, giveaway_id: str, current_winners: int):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.winners = discord.ui.TextInput(
            label="New Winners Count",
            placeholder="Enter number of winners...",
            default=str(current_winners),
            style=discord.TextStyle.short,
            max_length=2
        )
        self.add_item(self.winners)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle winners count update"""
        if self.giveaway_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        try:
            winners_count = int(self.winners.value)
            if winners_count < 1:
                await interaction.response.send_message("❌ Winners count must be at least 1!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number!", ephemeral=True)
            return
        
        active_giveaways[self.giveaway_id]['winners_count'] = winners_count
        
        try:
            channel = bot.get_channel(active_giveaways[self.giveaway_id]['channel_id'])
            message = await channel.fetch_message(active_giveaways[self.giveaway_id]['message_id'])
            embed = message.embeds[0]
            
            for i, field in enumerate(embed.fields):
                if field.name == "Winners":
                    embed.set_field_at(i, name="Winners", value=f"**{winners_count}**", inline=True)
                    break
            
            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating winners: {e}")
        
        save_giveaways()
        
        await interaction.response.send_message(f"✅ Winners count updated to: **{winners_count}**", ephemeral=True)
        await log_to_audit_channel(interaction.guild.id,
                                 f"✏️ {interaction.user.mention} updated winners to {winners_count} for giveaway ID: {self.giveaway_id}")


class DurationEditModal(discord.ui.Modal, title="Edit Giveaway Duration"):
    def __init__(self, giveaway_id: str):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.duration = discord.ui.TextInput(
            label="New Duration",
            placeholder="e.g., 1h, 30m, 2d (adds to current time)",
            style=discord.TextStyle.short,
            max_length=10
        )
        self.add_item(self.duration)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle duration update"""
        if self.giveaway_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        duration_seconds = convert_duration(self.duration.value)
        if duration_seconds == -1:
            await interaction.response.send_message("❌ Invalid duration! Use format like: 1h, 30m, 2d", ephemeral=True)
            return
        
        new_end_time = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
        active_giveaways[self.giveaway_id]['end_time'] = new_end_time
        
        try:
            channel = bot.get_channel(active_giveaways[self.giveaway_id]['channel_id'])
            message = await channel.fetch_message(active_giveaways[self.giveaway_id]['message_id'])
            embed = message.embeds[0]
            
            embed.timestamp = new_end_time
            
            for i, field in enumerate(embed.fields):
                if field.name == "Ends":
                    embed.set_field_at(i, name="Ends", value=f"<t:{int(new_end_time.timestamp())}:R>", inline=True)
                    break
            
            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating duration: {e}")
        
        await end_giveaway(self.giveaway_id, duration_seconds)
        save_giveaways()
        
        await interaction.response.send_message(f"✅ Duration updated! New end time: <t:{int(new_end_time.timestamp())}:R>", ephemeral=True)
        await log_to_audit_channel(interaction.guild.id,
                                 f"✏️ {interaction.user.mention} updated duration for giveaway ID: {self.giveaway_id} to {self.duration.value}")


class DescriptionEditModal(discord.ui.Modal, title="Edit Giveaway Description"):
    def __init__(self, giveaway_id: str, current_description: str = None):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.description = discord.ui.TextInput(
            label="New Description",
            placeholder="Enter description (leave empty to remove)",
            default=current_description or "",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.add_item(self.description)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle description update"""
        if self.giveaway_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        try:
            channel = bot.get_channel(active_giveaways[self.giveaway_id]['channel_id'])
            message = await channel.fetch_message(active_giveaways[self.giveaway_id]['message_id'])
            embed = message.embeds[0]
            
            new_fields = []
            description_exists = False
            
            for field in embed.fields:
                if field.name != "Description":
                    new_fields.append(field)
                else:
                    description_exists = True
            
            if self.description.value.strip():
                embed.clear_fields()
                embed.add_field(name="Description", value=self.description.value, inline=False)
                for field in new_fields:
                    embed.add_field(name=field.name, value=field.value, inline=field.inline)
            else:
                embed.clear_fields()
                for field in new_fields:
                    embed.add_field(name=field.name, value=field.value, inline=field.inline)
            
            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating description: {e}")
        
        await interaction.response.send_message(f"✅ Description updated!", ephemeral=True)
        await log_to_audit_channel(interaction.guild.id,
                                 f"✏️ {interaction.user.mention} updated description for giveaway ID: {self.giveaway_id}")


class RolesEditModal(discord.ui.Modal, title="Edit Allowed Roles"):
    def __init__(self, giveaway_id: str, current_roles: str = ""):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.roles = discord.ui.TextInput(
            label="Allowed Roles (space-separated mentions)",
            placeholder="e.g., @Role1 @Role2 (leave empty to allow all)",
            default=current_roles,
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )
        self.add_item(self.roles)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle roles update"""
        if self.giveaway_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        allowed_role_ids = []
        if self.roles.value:
            for role_mention in self.roles.value.split():
                if role_mention.startswith('<@&') and role_mention.endswith('>'):
                    try:
                        role_id = int(role_mention[3:-1])
                        allowed_role_ids.append(role_id)
                    except ValueError:
                        pass
        
        active_giveaways[self.giveaway_id]['allowed_roles'] = allowed_role_ids
        
        try:
            channel = bot.get_channel(active_giveaways[self.giveaway_id]['channel_id'])
            message = await channel.fetch_message(active_giveaways[self.giveaway_id]['message_id'])
            embed = message.embeds[0]
            
            new_fields = []
            roles_field_exists = False
            
            for field in embed.fields:
                if field.name != "Required Roles":
                    new_fields.append(field)
                else:
                    roles_field_exists = True
            
            if allowed_role_ids:
                role_mentions = " ".join([f"<@&{role_id}>" for role_id in allowed_role_ids])
                embed.clear_fields()
                for field in new_fields:
                    embed.add_field(name=field.name, value=field.value, inline=field.inline)
                embed.add_field(name="Required Roles", value=role_mentions, inline=False)
            else:
                embed.clear_fields()
                for field in new_fields:
                    embed.add_field(name=field.name, value=field.value, inline=field.inline)
            
            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating roles: {e}")
        
        save_giveaways()
        
        role_count = len(allowed_role_ids)
        await interaction.response.send_message(f"✅ Allowed roles updated! ({role_count} roles)", ephemeral=True)
        await log_to_audit_channel(interaction.guild.id,
                                 f"✏️ {interaction.user.mention} updated allowed roles for giveaway ID: {self.giveaway_id}")


class WinnerRoleEditModal(discord.ui.Modal, title="Edit Winner Role"):
    def __init__(self, giveaway_id: str, current_role: str = ""):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.role = discord.ui.TextInput(
            label="Winner Role (mention or leave empty to remove)",
            placeholder="e.g., @Winner",
            default=current_role,
            style=discord.TextStyle.short,
            max_length=100,
            required=False
        )
        self.add_item(self.role)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle winner role update"""
        if self.giveaway_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        winner_role_id = None
        if self.role.value.strip():
            role_text = self.role.value.strip()
            if role_text.startswith('<@&') and role_text.endswith('>'):
                try:
                    winner_role_id = int(role_text[3:-1])
                except ValueError:
                    await interaction.response.send_message("❌ Invalid role format! Use @RoleName", ephemeral=True)
                    return
            else:
                guild = interaction.guild
                role = discord.utils.find(lambda r: r.name.lower() == role_text.lower(), guild.roles)
                if role:
                    winner_role_id = role.id
                else:
                    await interaction.response.send_message("❌ Role not found!", ephemeral=True)
                    return
        
        active_giveaways[self.giveaway_id]['winner_role'] = winner_role_id
        save_giveaways()
        
        if winner_role_id:
            await interaction.response.send_message(f"✅ Winner role updated to <@&{winner_role_id}>!", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Winner role removed!", ephemeral=True)
        
        await log_to_audit_channel(interaction.guild.id,
                                 f"✏️ {interaction.user.mention} updated winner role for giveaway ID: {self.giveaway_id}")


class DMMessageEditModal(discord.ui.Modal, title="Edit DM Message"):
    def __init__(self, giveaway_id: str, current_message: str = ""):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.message = discord.ui.TextInput(
            label="DM Message to Winners",
            placeholder="Message sent to winners via DM...",
            default=current_message,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.add_item(self.message)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle DM message update"""
        if self.giveaway_id not in active_giveaways:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return
        
        active_giveaways[self.giveaway_id]['dm_message'] = self.message.value
        save_giveaways()
        
        await interaction.response.send_message("✅ DM message updated!", ephemeral=True)
        await log_to_audit_channel(interaction.guild.id,
                                 f"✏️ {interaction.user.mention} updated DM message for giveaway ID: {self.giveaway_id}")


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: str):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.participants = set()

    @discord.ui.button(label="Join Giveaway!", style=discord.ButtonStyle.primary, emoji="🎉", custom_id="join_giveaway")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        error_msg = await check_participation_requirements(interaction)
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return

        error_msg = await check_role_requirements(interaction, self.giveaway_id)
        if error_msg:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return

        if interaction.user.id in self.participants:
            leave_view = discord.ui.View(timeout=180)
            leave_button = discord.ui.Button(
                label="Leave Giveaway",
                style=discord.ButtonStyle.danger,
                emoji="🚪",
                custom_id=f"leave_{self.giveaway_id}"
            )

            async def leave_callback(interaction: discord.Interaction):
                if interaction.user.id not in self.participants:
                    await interaction.response.send_message("❌ You are not participating in this giveaway!",
                                                            ephemeral=True)
                    return

                self.participants.remove(interaction.user.id)
                await update_participant_count(self.giveaway_id)
                save_giveaways()

                await interaction.response.send_message("✅ You have left the giveaway!", ephemeral=True)
                await log_to_audit_channel(interaction.guild.id,
                                         f"🚪 {interaction.user.mention} left giveaway: **{active_giveaways[self.giveaway_id]['prize']}** (ID: {self.giveaway_id})")

            leave_button.callback = leave_callback
            leave_view.add_item(leave_button)

            await interaction.response.send_message(
                f"❌ You are already participating in this giveaway! (ID: `{self.giveaway_id}`)\n"
                "Click the button below to leave the giveaway.",
                view=leave_view,
                ephemeral=True
            )
            return

        self.participants.add(interaction.user.id)
        await interaction.response.send_message(
            f"✅ You have joined the giveaway! Good luck! 🎉\n**Giveaway ID:** `{self.giveaway_id}`", ephemeral=True)

        await update_participant_count(self.giveaway_id)
        save_giveaways()
        update_user_statistics(interaction.guild.id, interaction.user.id, "participations", 1)

    @discord.ui.button(label="Show Participants", style=discord.ButtonStyle.secondary, emoji="👥",
                       custom_id="show_participants")
    async def show_participants_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Shows the list of all participants"""
        if not self.participants:
            await interaction.response.send_message("❌ No one has joined this giveaway yet.", ephemeral=True)
            return

        participants_list = []
        for user_id in self.participants:
            member = interaction.guild.get_member(user_id)
            if member:
                participants_list.append(member.display_name)

        total_participants = len(participants_list)

        if total_participants > 20:
            display_list = participants_list[:20]
            remaining = total_participants - 20
        else:
            display_list = participants_list
            remaining = 0

        embed = discord.Embed(
            title=f"🎉 Participant List ({total_participants} participants)",
            description=f"**Giveaway ID:** `{self.giveaway_id}`",
            color=discord.Color.blue()
        )

        if display_list:
            chunks = [display_list[i:i + 10] for i in range(0, len(display_list), 10)]

            for i, chunk in enumerate(chunks):
                participants_text = "\n".join([f"• {name}" for name in chunk])
                embed.add_field(
                    name=f"Participants {i + 1}" if len(chunks) > 1 else "Participants",
                    value=participants_text,
                    inline=True
                )

        if remaining > 0:
            embed.add_field(
                name="More Participants",
                value=f"... and {remaining} more participants",
                inline=False
            )

        embed.set_footer(text="Giveaway Participant List")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# Data management functions
def load_data():
    """Loads all data from files"""
    global active_giveaways, server_settings, user_statistics, ended_giveaways

    # Load giveaways
    if os.path.exists(GIVEAWAY_FILE):
        try:
            with open(GIVEAWAY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for guild_id, guild_giveaways in data.items():
                for giveaway_id, giveaway_data in guild_giveaways.items():
                    participants_set = set(giveaway_data.get('participants', []))

                    view = GiveawayView(giveaway_id)
                    view.participants = participants_set

                    end_time = datetime.datetime.fromisoformat(giveaway_data['end_time'])

                    active_giveaways[giveaway_id] = {
                        'message_id': giveaway_data['message_id'],
                        'channel_id': giveaway_data['channel_id'],
                        'guild_id': int(guild_id),
                        'prize': giveaway_data['prize'],
                        'winners_count': giveaway_data['winners_count'],
                        'end_time': end_time,
                        'view': view,
                        'creator_id': giveaway_data['creator_id'],
                        'allowed_roles': giveaway_data.get('allowed_roles', []),
                        'winner_role': giveaway_data.get('winner_role'),
                        'dm_message': giveaway_data.get('dm_message')
                    }

                    remaining_time = (end_time - datetime.datetime.now().astimezone()).total_seconds()
                    if remaining_time > 0:
                        asyncio.create_task(end_giveaway(giveaway_id, remaining_time))
                    else:
                        asyncio.create_task(end_giveaway(giveaway_id, 0))

            logger.info(f"✅ {len(active_giveaways)} giveaways loaded")
        except Exception as e:
            logger.error(f"❌ Error loading giveaways: {e}")

    # Load server settings
    if os.path.exists(SERVER_SETTINGS_FILE):
        try:
            with open(SERVER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                server_settings = json.load(f)
            logger.info("✅ Server settings loaded")
        except Exception as e:
            logger.error(f"❌ Error loading server settings: {e}")

    # Load user statistics
    if os.path.exists(STATISTICS_FILE):
        try:
            with open(STATISTICS_FILE, 'r', encoding='utf-8') as f:
                user_statistics = json.load(f)
            logger.info("✅ User statistics loaded")
        except Exception as e:
            logger.error(f"❌ Error loading user statistics: {e}")

    # Load ended giveaways
    if os.path.exists(ENDED_GIVEAWAYS_FILE):
        try:
            with open(ENDED_GIVEAWAYS_FILE, 'r', encoding='utf-8') as f:
                ended_giveaways = json.load(f)
            logger.info(f"✅ {sum(len(g) for g in ended_giveaways.values())} ended giveaways loaded")
        except Exception as e:
            logger.error(f"❌ Error loading ended giveaways: {e}")

def save_giveaways():
    """Saves giveaways to JSON file"""
    try:
        data = {}

        for giveaway_id, giveaway_data in active_giveaways.items():
            guild_id = str(giveaway_data['guild_id'])

            if guild_id not in data:
                data[guild_id] = {}

            data[guild_id][giveaway_id] = {
                'message_id': giveaway_data['message_id'],
                'channel_id': giveaway_data['channel_id'],
                'prize': giveaway_data['prize'],
                'winners_count': giveaway_data['winners_count'],
                'end_time': giveaway_data['end_time'].isoformat(),
                'creator_id': giveaway_data['creator_id'],
                'participants': list(giveaway_data['view'].participants),
                'allowed_roles': giveaway_data.get('allowed_roles', []),
                'winner_role': giveaway_data.get('winner_role'),
                'dm_message': giveaway_data.get('dm_message')
            }

        with open(GIVEAWAY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"❌ Error saving giveaways: {e}")


def save_ended_giveaways():
    """Saves ended giveaways to JSON file"""
    try:
        with open(ENDED_GIVEAWAYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(ended_giveaways, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Error saving ended giveaways: {e}")


def save_server_settings():
    """Saves server settings to JSON file"""
    try:
        with open(SERVER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(server_settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Error saving server settings: {e}")


def save_user_statistics():
    """Saves user statistics to JSON file"""
    try:
        with open(STATISTICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_statistics, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Error saving user statistics: {e}")


def remove_giveaway_from_file(giveaway_id: str):
    """Removes a giveaway from the active giveaways file"""
    if os.path.exists(GIVEAWAY_FILE):
        try:
            with open(GIVEAWAY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for guild_id, guild_giveaways in data.items():
                if giveaway_id in guild_giveaways:
                    del guild_giveaways[giveaway_id]
                    if not guild_giveaways:
                        del data[guild_id]
                    break

            with open(GIVEAWAY_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"❌ Error removing giveaway: {e}")


def get_server_settings(guild_id: int):
    """Gets server settings, creating default if not exists"""
    guild_id_str = str(guild_id)
    if guild_id_str not in server_settings:
        server_settings[guild_id_str] = {
            'audit_channel': None,
            'min_participations': 0,
            'min_wins': 0,
            'min_losses': 0
        }
    return server_settings[guild_id_str]


def get_user_stats(guild_id: int, user_id: int):
    """Gets user statistics, creating default if not exists"""
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)

    if guild_id_str not in user_statistics:
        user_statistics[guild_id_str] = {}

    if user_id_str not in user_statistics[guild_id_str]:
        user_statistics[guild_id_str][user_id_str] = {
            'participations': 0,
            'wins': 0,
            'losses': 0
        }

    return user_statistics[guild_id_str][user_id_str]


def update_user_statistics(guild_id: int, user_id: int, stat_type: str, value: int = 1):
    """Updates user statistics"""
    stats = get_user_stats(guild_id, user_id)
    stats[stat_type] += value
    save_user_statistics()


async def check_participation_requirements(interaction: discord.Interaction):
    """Checks if user meets participation requirements"""
    settings = get_server_settings(interaction.guild.id)
    user_stats = get_user_stats(interaction.guild.id, interaction.user.id)

    if settings['min_participations'] > 0 and user_stats['participations'] < settings['min_participations']:
        return f"❌ You need at least {settings['min_participations']} total participations to join this giveaway!"

    if settings['min_wins'] > 0 and user_stats['wins'] < settings['min_wins']:
        return f"❌ You need at least {settings['min_wins']} wins to join this giveaway!"

    if settings['min_losses'] > 0 and user_stats['losses'] < settings['min_losses']:
        return f"❌ You need at least {settings['min_losses']} losses to join this giveaway!"

    return None


async def check_role_requirements(interaction: discord.Interaction, giveaway_id: str):
    """Checks if user has required roles for giveaway"""
    if giveaway_id not in active_giveaways:
        return None

    giveaway = active_giveaways[giveaway_id]
    allowed_roles = giveaway.get('allowed_roles', [])

    if not allowed_roles:
        return None

    user_roles = [role.id for role in interaction.user.roles]

    if not any(role_id in user_roles for role_id in allowed_roles):
        role_mentions = " ".join([f"<@&{role_id}>" for role_id in allowed_roles])
        return f"❌ This giveaway is only for members with these roles: {role_mentions}"

    return None


@bot.event
async def on_ready():
    print(f'{bot.user.name} is online!')

    load_data()

    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} slash commands synchronized")
    except Exception as e:
        print(f"❌ Error synchronizing commands: {e}")


# Giveaway Commands
@bot.tree.command(name="giveaway", description="Start a new giveaway")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    prize="What is the prize?",
    winners="How many winners should there be?",
    duration="How long should the giveaway run? (e.g., 1h, 30m, 2d)",
    channel="In which channel should the giveaway be posted?",
    description="Description of the giveaway (optional)",
    allowed_roles="Roles that can participate (optional)",
    winner_role="Role that winners will receive (optional)",
    dm_message="Message to send to winners via DM (optional)"
)
async def giveaway(
        interaction: discord.Interaction,
        prize: str,
        winners: int,
        duration: str,
        channel: Optional[discord.TextChannel] = None,
        description: Optional[str] = None,
        allowed_roles: Optional[str] = None,
        winner_role: Optional[discord.Role] = None,
        dm_message: Optional[str] = None
):
    """Slash Command to create a giveaway"""

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to create giveaways!",
                                                ephemeral=True)
        return

    if channel is None:
        channel = interaction.channel

    duration_seconds = convert_duration(duration)
    if duration_seconds == -1:
        await interaction.response.send_message("❌ Invalid duration! Use format like: 1h, 30m, 2d", ephemeral=True)
        return

    end_time = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
    timestamp = f"<t:{int(end_time.timestamp())}:R>"

    giveaway_id = generate_giveaway_id()

    allowed_role_ids = []
    if allowed_roles:
        for role_mention in allowed_roles.split():
            if role_mention.startswith('<@&') and role_mention.endswith('>'):
                try:
                    role_id = int(role_mention[3:-1])
                    allowed_role_ids.append(role_id)
                except ValueError:
                    pass

    embed = discord.Embed(
        title="🎉 **NEW GIVEAWAY!** 🎉",
        color=discord.Color.gold(),
        timestamp=end_time
    )

    if description:
        embed.add_field(name="Description", value=description, inline=False)

    embed.add_field(name="Prize", value=f"**{prize}**", inline=True)
    embed.add_field(name="Winners", value=f"**{winners}**", inline=True)
    embed.add_field(name="Ends", value=timestamp, inline=True)
    embed.add_field(name="Participants", value="0", inline=True)
    embed.add_field(name="Giveaway ID", value=f"`{giveaway_id}`", inline=True)

    if allowed_role_ids:
        role_mentions = " ".join([f"<@&{role_id}>" for role_id in allowed_role_ids])
        embed.add_field(name="Required Roles", value=role_mentions, inline=False)

    embed.set_footer(text=f"Started by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    view = GiveawayView(giveaway_id)

    await interaction.response.send_message(
        f"✅ Giveaway will be created in {channel.mention}!\n**Giveaway ID:** `{giveaway_id}`", ephemeral=True)

    giveaway_message = await channel.send(embed=embed, view=view)

    active_giveaways[giveaway_id] = {
        'message_id': giveaway_message.id,
        'channel_id': channel.id,
        'guild_id': interaction.guild.id,
        'prize': prize,
        'winners_count': winners,
        'end_time': end_time,
        'view': view,
        'creator_id': interaction.user.id,
        'message': giveaway_message,
        'allowed_roles': allowed_role_ids,
        'winner_role': winner_role.id if winner_role else None,
        'dm_message': dm_message
    }

    save_giveaways()
    asyncio.create_task(end_giveaway(giveaway_id, duration_seconds))
    await log_to_audit_channel(interaction.guild.id,
                             f"🎉 New giveaway created: **{prize}** in {channel.mention} by {interaction.user.mention} (ID: {giveaway_id})")


@bot.tree.command(name="giveaway_cancel", description="Cancel an active giveaway")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    giveaway_id="The ID of the giveaway to cancel"
)
async def giveaway_cancel(interaction: discord.Interaction, giveaway_id: str):
    """Cancel a giveaway"""

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions!", ephemeral=True)
        return

    giveaway_to_cancel = None
    giveaway_id_to_cancel = None

    for gid, giveaway_data in active_giveaways.items():
        if gid == giveaway_id and giveaway_data['guild_id'] == interaction.guild.id:
            giveaway_to_cancel = giveaway_data
            giveaway_id_to_cancel = gid
            break

    if not giveaway_to_cancel:
        await interaction.response.send_message("❌ No active giveaway found with this ID!", ephemeral=True)
        return

    if giveaway_to_cancel['creator_id'] != interaction.user.id and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You can only cancel your own giveaways!", ephemeral=True)
        return

    channel = bot.get_channel(giveaway_to_cancel['channel_id'])
    if channel:
        try:
            message = await channel.fetch_message(giveaway_to_cancel['message_id'])

            view = giveaway_to_cancel['view']
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
                    item.label = "Giveaway cancelled"
                    item.style = discord.ButtonStyle.danger

            embed = message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "🎉 **GIVEAWAY CANCELLED** 🎉"

            new_fields = []
            for field in embed.fields:
                if field.name != "Participants":
                    new_fields.append(field)

            embed.clear_fields()
            for field in new_fields:
                embed.add_field(name=field.name, value=field.value, inline=field.inline)

            embed.add_field(name="Status", value="❌ Giveaway was cancelled", inline=False)
            embed.add_field(name="Participants", value=str(len(view.participants)), inline=True)

            await message.edit(embed=embed, view=view)

            await interaction.response.send_message(
                f"✅ Giveaway for **{giveaway_to_cancel['prize']}** (ID: `{giveaway_id}`) has been cancelled!",
                ephemeral=True)
            await channel.send(
                f"❌ The giveaway for **{giveaway_to_cancel['prize']}** (ID: `{giveaway_id}`) has been cancelled by {interaction.user.mention}!")

        except discord.NotFound:
            await interaction.response.send_message("❌ Giveaway message not found!", ephemeral=True)

    if giveaway_id_to_cancel in active_giveaways:
        del active_giveaways[giveaway_id_to_cancel]
    remove_giveaway_from_file(giveaway_id_to_cancel)

    await log_to_audit_channel(interaction.guild.id,
                             f"❌ Giveaway cancelled: **{giveaway_to_cancel['prize']}** by {interaction.user.mention} (ID: {giveaway_id})")


@bot.tree.command(name="giveaway_list", description="Show all active giveaways with edit options")
@app_commands.default_permissions(administrator=True)
async def giveaway_list(interaction: discord.Interaction):
    """List all active giveaways with edit buttons"""

    guild_giveaways = {k: v for k, v in active_giveaways.items() if v['guild_id'] == interaction.guild.id}

    if not guild_giveaways:
        await interaction.response.send_message("❌ There are currently no active giveaways!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎉 Active Giveaways",
        description=f"Total active giveaways: **{len(guild_giveaways)}**\n\nSelect a giveaway below to edit it:",
        color=discord.Color.blue()
    )
    
    options = []
    
    for giveaway_id, data in guild_giveaways.items():
        channel = bot.get_channel(data['channel_id'])
        time_left = f"<t:{int(data['end_time'].timestamp())}:R>"
        
        embed.add_field(
            name=f"{data['prize']} (ID: `{giveaway_id}`)",
            value=f"• Channel: {channel.mention if channel else 'Unknown'}\n• Winners: {data['winners_count']}\n• Ends: {time_left}\n• Participants: {len(data['view'].participants)}",
            inline=False
        )
        
        truncated_prize = data['prize'][:90] + "..." if len(data['prize']) > 90 else data['prize']
        options.append(
            discord.SelectOption(
                label=truncated_prize,
                description=f"ID: {giveaway_id} | Ends {time_left}",
                value=giveaway_id,
                emoji="🎉"
            )
        )
    
    class GiveawaySelectView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            select = discord.ui.Select(
                placeholder="Select a giveaway to edit...",
                options=options[:25]
            )
            select.callback = self.select_callback
            self.add_item(select)
        
        async def select_callback(self, interaction: discord.Interaction):
            selected_id = interaction.data['values'][0]
            if selected_id in active_giveaways and active_giveaways[selected_id]['guild_id'] == interaction.guild.id:
                edit_view = GiveawayEditView(selected_id, interaction)
                
                giveaway = active_giveaways[selected_id]
                channel = bot.get_channel(giveaway['channel_id'])
                time_left = f"<t:{int(giveaway['end_time'].timestamp())}:R>"
                
                info_embed = discord.Embed(
                    title=f"🎉 Edit Giveaway: {giveaway['prize']}",
                    description=f"**Giveaway ID:** `{selected_id}`\n\nSelect what you want to edit:",
                    color=discord.Color.gold()
                )
                
                info_embed.add_field(name="Prize", value=giveaway['prize'], inline=True)
                info_embed.add_field(name="Winners", value=giveaway['winners_count'], inline=True)
                info_embed.add_field(name="Ends", value=time_left, inline=True)
                info_embed.add_field(name="Channel", value=channel.mention if channel else "Unknown", inline=True)
                info_embed.add_field(name="Participants", value=len(giveaway['view'].participants), inline=True)
                
                if giveaway.get('allowed_roles'):
                    role_mentions = " ".join([f"<@&{role_id}>" for role_id in giveaway['allowed_roles']])
                    info_embed.add_field(name="Allowed Roles", value=role_mentions, inline=False)
                
                if giveaway.get('winner_role'):
                    info_embed.add_field(name="Winner Role", value=f"<@&{giveaway['winner_role']}>", inline=False)
                
                if giveaway.get('dm_message'):
                    info_embed.add_field(name="DM Message", value=giveaway['dm_message'][:100] + "..." if len(giveaway['dm_message']) > 100 else giveaway['dm_message'], inline=False)
                
                await interaction.response.send_message(embed=info_embed, view=edit_view, ephemeral=True)
            else:
                await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
    
    await interaction.response.send_message(embed=embed, view=GiveawaySelectView(), ephemeral=True)


@bot.tree.command(name="giveaway_edit", description="Edit a specific giveaway")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    giveaway_id="The ID of the giveaway to edit"
)
async def giveaway_edit(interaction: discord.Interaction, giveaway_id: str):
    """Edit a specific giveaway"""
    
    if giveaway_id not in active_giveaways or active_giveaways[giveaway_id]['guild_id'] != interaction.guild.id:
        await interaction.response.send_message("❌ No active giveaway found with this ID in your server!", ephemeral=True)
        return
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to edit giveaways!", ephemeral=True)
        return
    
    edit_view = GiveawayEditView(giveaway_id, interaction)
    
    giveaway = active_giveaways[giveaway_id]
    channel = bot.get_channel(giveaway['channel_id'])
    time_left = f"<t:{int(giveaway['end_time'].timestamp())}:R>"
    
    embed = discord.Embed(
        title=f"🎉 Edit Giveaway: {giveaway['prize']}",
        description=f"**Giveaway ID:** `{giveaway_id}`\n\nSelect what you want to edit:",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="Prize", value=giveaway['prize'], inline=True)
    embed.add_field(name="Winners", value=giveaway['winners_count'], inline=True)
    embed.add_field(name="Ends", value=time_left, inline=True)
    embed.add_field(name="Channel", value=channel.mention if channel else "Unknown", inline=True)
    embed.add_field(name="Participants", value=len(giveaway['view'].participants), inline=True)
    
    if giveaway.get('allowed_roles'):
        role_mentions = " ".join([f"<@&{role_id}>" for role_id in giveaway['allowed_roles']])
        embed.add_field(name="Allowed Roles", value=role_mentions, inline=False)
    
    if giveaway.get('winner_role'):
        embed.add_field(name="Winner Role", value=f"<@&{giveaway['winner_role']}>", inline=False)
    
    if giveaway.get('dm_message'):
        embed.add_field(name="DM Message", value=giveaway['dm_message'][:100] + "..." if len(giveaway['dm_message']) > 100 else giveaway['dm_message'], inline=False)
    
    await interaction.response.send_message(embed=embed, view=edit_view, ephemeral=True)


# KORRIGIERTER Reroll Command
@bot.tree.command(name="giveaway_reroll", description="Reroll new winners for an ended giveaway")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    giveaway_id="The ID of the giveaway to reroll",
    winners_count="Number of winners to reroll (leave empty for original winner count)"
)
async def giveaway_reroll(interaction: discord.Interaction, giveaway_id: str, winners_count: Optional[int] = None):
    """Reroll winners for a giveaway"""
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to reroll giveaways!", ephemeral=True)
        return
    
    # Prüfe zuerst in den beendeten Giveaways
    guild_id_str = str(interaction.guild.id)
    
    if guild_id_str in ended_giveaways and giveaway_id in ended_giveaways[guild_id_str]:
        giveaway_data = ended_giveaways[guild_id_str][giveaway_id]
        participants = giveaway_data.get('participants', [])
        
        if not participants:
            await interaction.response.send_message("❌ No participants found for this giveaway!", ephemeral=True)
            return
        
        # Use original winners count if not specified
        if winners_count is None:
            winners_count = giveaway_data['winners_count']
        
        if winners_count > len(participants):
            await interaction.response.send_message(f"❌ Not enough participants! Only {len(participants)} participants available.", ephemeral=True)
            return
        
        # Select new winners
        new_winners = random.sample(participants, winners_count)
        
        # Get member objects
        winner_members = []
        for winner_id in new_winners:
            member = interaction.guild.get_member(int(winner_id))
            if member:
                winner_members.append(member)
        
        if not winner_members:
            await interaction.response.send_message("❌ Could not find any of the winners in the server!", ephemeral=True)
            return
        
        # Create announcement
        channel = bot.get_channel(giveaway_data['channel_id'])
        if channel:
            winners_text = ", ".join(winner.mention for winner in winner_members)
            
            embed = discord.Embed(
                title="🎉 **GIVEAWAY REROLL!** 🎉",
                description=f"New winners have been selected for the giveaway: **{giveaway_data['prize']}**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="🎁 Prize", value=giveaway_data['prize'], inline=True)
            embed.add_field(name="🏆 New Winners", value=winners_text, inline=False)
            embed.add_field(name="📋 Giveaway ID", value=f"`{giveaway_id}`", inline=True)
            embed.add_field(name="👥 Total Participants", value=str(len(participants)), inline=True)
            
            embed.set_footer(text=f"Rerolled by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            
            await channel.send(embed=embed)
            
            # Send DM to new winners if message exists
            dm_message = giveaway_data.get('dm_message')
            if dm_message:
                for winner in winner_members:
                    try:
                        dm_embed = discord.Embed(
                            title="🎉 Congratulations! You won a reroll!",
                            description=f"You have been selected as a new winner for: **{giveaway_data['prize']}**",
                            color=discord.Color.gold()
                        )
                        dm_embed.add_field(name="Prize Details", value=dm_message, inline=False)
                        dm_embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
                        await winner.send(embed=dm_embed)
                    except Exception as e:
                        print(f"Error sending DM to winner: {e}")
            
            # Assign winner role if specified
            winner_role_id = giveaway_data.get('winner_role')
            if winner_role_id and winner_members:
                role = interaction.guild.get_role(int(winner_role_id))
                if role:
                    for winner in winner_members:
                        try:
                            await winner.add_roles(role)
                        except Exception as e:
                            print(f"Error assigning role to winner: {e}")
            
            await interaction.response.send_message(
                f"✅ Successfully rerolled giveaway **{giveaway_data['prize']}**!\n"
                f"New winners: {winners_text}",
                ephemeral=True
            )
            
            await log_to_audit_channel(interaction.guild.id,
                                     f"🔄 {interaction.user.mention} rerolled giveaway: **{giveaway_data['prize']}** (ID: {giveaway_id}) with {winners_count} new winners")
        else:
            await interaction.response.send_message("❌ Could not find the giveaway channel!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No ended giveaway found with this ID in your server!", ephemeral=True)


# Statistics and Leaderboard Commands
@bot.tree.command(name="stats", description="Show giveaway statistics for this server")
async def stats(interaction: discord.Interaction):
    """Show server giveaway statistics"""

    guild_id = interaction.guild.id
    total_giveaways = sum(1 for g in active_giveaways.values() if g['guild_id'] == guild_id)

    if str(guild_id) in user_statistics:
        total_participations = sum(stats['participations'] for stats in user_statistics[str(guild_id)].values())
        total_wins = sum(stats['wins'] for stats in user_statistics[str(guild_id)].values())
    else:
        total_participations = 0
        total_wins = 0

    embed = discord.Embed(
        title="📊 Giveaway Statistics",
        description=f"Statistics for **{interaction.guild.name}**",
        color=discord.Color.blue()
    )

    embed.add_field(name="Active Giveaways", value=total_giveaways, inline=True)
    embed.add_field(name="Total Participations", value=total_participations, inline=True)
    embed.add_field(name="Total Wins", value=total_wins, inline=True)

    if str(guild_id) in user_statistics and user_statistics[str(guild_id)]:
        top_winners = sorted(
            [(user_id, stats['wins']) for user_id, stats in user_statistics[str(guild_id)].items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]

        winners_text = ""
        for i, (user_id, wins) in enumerate(top_winners):
            member = interaction.guild.get_member(int(user_id))
            if member:
                winners_text += f"{i + 1}. {member.display_name}: {wins} wins\n"

        if winners_text:
            embed.add_field(name="🏆 Top Winners", value=winners_text, inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="Show the winner leaderboard for this server")
async def leaderboard(interaction: discord.Interaction):
    """Show winner leaderboard"""

    guild_id = interaction.guild.id

    if str(guild_id) not in user_statistics or not user_statistics[str(guild_id)]:
        await interaction.response.send_message("❌ No giveaway statistics available for this server yet!",
                                                ephemeral=True)
        return

    top_winners = sorted(
        [(user_id, stats) for user_id, stats in user_statistics[str(guild_id)].items()],
        key=lambda x: x[1]['wins'],
        reverse=True
    )[:10]

    embed = discord.Embed(
        title="🏆 Giveaway Leaderboard",
        description=f"Top winners in **{interaction.guild.name}**",
        color=discord.Color.gold()
    )

    leaderboard_text = ""
    for i, (user_id, stats) in enumerate(top_winners):
        member = interaction.guild.get_member(int(user_id))
        if member:
            win_rate = (stats['wins'] / stats['participations'] * 100) if stats['participations'] > 0 else 0
            leaderboard_text += f"**{i + 1}. {member.display_name}**\n"
            leaderboard_text += f"   🏆 Wins: {stats['wins']} | 📊 Participations: {stats['participations']} | 📈 Win Rate: {win_rate:.1f}%\n\n"

    embed.description = leaderboard_text if leaderboard_text else "No winners yet!"

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="my_stats", description="Show your personal giveaway statistics")
async def my_stats(interaction: discord.Interaction):
    """Show personal statistics"""

    guild_id = interaction.guild.id
    user_id = interaction.user.id

    stats = get_user_stats(guild_id, user_id)

    win_rate = (stats['wins'] / stats['participations'] * 100) if stats['participations'] > 0 else 0

    embed = discord.Embed(
        title="📊 Your Giveaway Statistics",
        color=discord.Color.blue()
    )

    embed.add_field(name="Participations", value=stats['participations'], inline=True)
    embed.add_field(name="Wins", value=stats['wins'], inline=True)
    embed.add_field(name="Losses", value=stats['losses'], inline=True)
    embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# Server Settings Commands
@bot.tree.command(name="set_audit_channel", description="Set the audit log channel for giveaways")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    channel="The channel where giveaway logs will be sent"
)
async def set_audit_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set audit log channel"""

    settings = get_server_settings(interaction.guild.id)
    settings['audit_channel'] = channel.id
    save_server_settings()

    await interaction.response.send_message(f"✅ Audit log channel set to {channel.mention}!", ephemeral=True)


@bot.tree.command(name="set_participation_requirements",
                  description="Set minimum requirements for giveaway participation")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    min_participations="Minimum total participations required (0 to disable)",
    min_wins="Minimum wins required (0 to disable)",
    min_losses="Minimum losses required (0 to disable)"
)
async def set_participation_requirements(
        interaction: discord.Interaction,
        min_participations: int = 0,
        min_wins: int = 0,
        min_losses: int = 0
):
    """Set participation requirements"""

    settings = get_server_settings(interaction.guild.id)
    settings['min_participations'] = max(0, min_participations)
    settings['min_wins'] = max(0, min_wins)
    settings['min_losses'] = max(0, min_losses)
    save_server_settings()

    requirements = []
    if min_participations > 0:
        requirements.append(f"Minimum participations: {min_participations}")
    if min_wins > 0:
        requirements.append(f"Minimum wins: {min_wins}")
    if min_losses > 0:
        requirements.append(f"Minimum losses: {min_losses}")

    if requirements:
        requirements_text = "\n".join(requirements)
        await interaction.response.send_message(f"✅ Participation requirements set:\n{requirements_text}",
                                                ephemeral=True)
    else:
        await interaction.response.send_message("✅ All participation requirements have been disabled!", ephemeral=True)


# Export Commands
@bot.tree.command(name="export_participants", description="Export participants of a specific giveaway")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    giveaway_id="The ID of the giveaway to export from"
)
async def export_participants(interaction: discord.Interaction, giveaway_id: str):
    """Export participants of a giveaway"""

    giveaway_data = None
    for gid, data in active_giveaways.items():
        if gid == giveaway_id and data['guild_id'] == interaction.guild.id:
            giveaway_data = data
            break

    if not giveaway_data:
        await interaction.response.send_message("❌ No giveaway found with this ID in your server!", ephemeral=True)
        return

    participants = list(giveaway_data['view'].participants)

    if not participants:
        await interaction.response.send_message("❌ No participants to export!", ephemeral=True)
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'Username', 'Display Name'])

    for user_id in participants:
        member = interaction.guild.get_member(user_id)
        if member:
            writer.writerow([user_id, str(member), member.display_name])
        else:
            writer.writerow([user_id, 'Unknown', 'Unknown'])

    output.seek(0)
    file = discord.File(io.BytesIO(output.getvalue().encode('utf-8')), filename=f"participants_{giveaway_id}.csv")

    embed = discord.Embed(
        title="📊 Participants Export",
        description=f"Exported {len(participants)} participants from giveaway: **{giveaway_data['prize']}** (ID: `{giveaway_id}`)",
        color=discord.Color.green()
    )

    await interaction.response.send_message(embed=embed, file=file, ephemeral=True)


# Leave Giveaway Command
@bot.tree.command(name="leave_giveaway", description="Leave a giveaway you've joined")
@app_commands.describe(
    giveaway_id="The ID of the giveaway to leave"
)
async def leave_giveaway(interaction: discord.Interaction, giveaway_id: str):
    """Leave a giveaway"""

    giveaway_data = None
    for gid, data in active_giveaways.items():
        if gid == giveaway_id and data['guild_id'] == interaction.guild.id:
            giveaway_data = data
            break

    if not giveaway_data:
        await interaction.response.send_message("❌ No giveaway found with this ID in your server!", ephemeral=True)
        return

    view = giveaway_data['view']

    if interaction.user.id not in view.participants:
        await interaction.response.send_message("❌ You are not participating in this giveaway!", ephemeral=True)
        return

    view.participants.remove(interaction.user.id)
    await update_participant_count(giveaway_id)
    save_giveaways()

    await interaction.response.send_message(f"✅ You have left the giveaway **{giveaway_data['prize']}**!",
                                            ephemeral=True)
    await log_to_audit_channel(interaction.guild.id,
                             f"🚪 {interaction.user.mention} left giveaway: **{giveaway_data['prize']}** (ID: {giveaway_id})")


# Utility Functions
def convert_duration(duration: str) -> int:
    """Converts duration string to seconds"""
    units = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }

    try:
        unit = duration[-1].lower()
        if unit not in units:
            return -1

        number = int(duration[:-1])
        return number * units[unit]
    except (ValueError, IndexError):
        return -1


async def update_participant_count(giveaway_id: str):
    """Updates participant count in giveaway embed"""
    if giveaway_id not in active_giveaways:
        return

    giveaway_data = active_giveaways[giveaway_id]
    view = giveaway_data['view']

    try:
        if 'message' in giveaway_data:
            embed = giveaway_data['message'].embeds[0]
        else:
            channel = bot.get_channel(giveaway_data['channel_id'])
            message = await channel.fetch_message(giveaway_data['message_id'])
            embed = message.embeds[0]
            giveaway_data['message'] = message

        for i, field in enumerate(embed.fields):
            if field.name == "Participants":
                embed.set_field_at(i, name="Participants", value=str(len(view.participants)), inline=True)
                break

        await giveaway_data['message'].edit(embed=embed)
    except Exception as e:
        print(f"Error updating participant count: {e}")


async def log_to_audit_channel(guild_id: int, message: str):
    """Logs message to audit channel if set"""
    settings = get_server_settings(guild_id)
    audit_channel_id = settings.get('audit_channel')

    if audit_channel_id:
        channel = bot.get_channel(audit_channel_id)
        if channel:
            embed = discord.Embed(
                description=message,
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            await channel.send(embed=embed)


async def end_giveaway(giveaway_id: str, delay: int):
    """Ends the giveaway after the specified time"""
    if delay > 0:
        await asyncio.sleep(delay)

    if giveaway_id not in active_giveaways:
        return

    giveaway_data = active_giveaways[giveaway_id]
    view = giveaway_data['view']

    # Bevor wir das Giveaway entfernen, speichern wir es für Rerolls
    guild_id_str = str(giveaway_data['guild_id'])
    
    # Speichere das beendete Giveaway für Rerolls
    if guild_id_str not in ended_giveaways:
        ended_giveaways[guild_id_str] = {}
    
    ended_giveaways[guild_id_str][giveaway_id] = {
        'message_id': giveaway_data['message_id'],
        'channel_id': giveaway_data['channel_id'],
        'prize': giveaway_data['prize'],
        'winners_count': giveaway_data['winners_count'],
        'end_time': giveaway_data['end_time'].isoformat(),
        'creator_id': giveaway_data['creator_id'],
        'participants': list(view.participants),
        'allowed_roles': giveaway_data.get('allowed_roles', []),
        'winner_role': giveaway_data.get('winner_role'),
        'dm_message': giveaway_data.get('dm_message')
    }
    
    # Speichere die beendeten Giveaways
    save_ended_giveaways()

    for item in view.children:
        if isinstance(item, discord.ui.Button):
            item.disabled = True
            if item.custom_id == "join_giveaway":
                item.label = "Giveaway ended"
                item.style = discord.ButtonStyle.secondary
            elif item.custom_id == "show_participants":
                item.label = "Show participants"

    try:
        channel = bot.get_channel(giveaway_data['channel_id'])
        if channel is None:
            return

        message = await channel.fetch_message(giveaway_data['message_id'])
        participants = list(view.participants)

        if not participants:
            embed = message.embeds[0]
            embed.color = discord.Color.red()
            embed.title = "🎉 **GIVEAWAY ENDED** 🎉"

            new_fields = []
            for field in embed.fields:
                if field.name != "Participants":
                    new_fields.append(field)

            embed.clear_fields()
            for field in new_fields:
                embed.add_field(name=field.name, value=field.value, inline=field.inline)

            embed.add_field(name="Result", value="❌ No one participated in this giveaway!", inline=False)
            embed.add_field(name="Participants", value=str(len(view.participants)), inline=True)

            await message.edit(embed=embed, view=view)
            await channel.send(
                f"❌ The giveaway for **{giveaway_data['prize']}** (ID: `{giveaway_id}`) ended, but there were no participants!")
        else:
            winners_count = min(giveaway_data['winners_count'], len(participants))
            winner_ids = random.sample(participants, winners_count)

            winners = []
            for winner_id in winner_ids:
                member = channel.guild.get_member(winner_id)
                if member:
                    winners.append(member)

            winners_text = ", ".join(winner.mention for winner in winners) if winners else "No winners"

            winner_role_id = giveaway_data.get('winner_role')
            if winner_role_id and winners:
                role = channel.guild.get_role(winner_role_id)
                if role:
                    for winner in winners:
                        try:
                            await winner.add_roles(role)
                        except Exception as e:
                            print(f"Error assigning role to winner: {e}")

            dm_message = giveaway_data.get('dm_message')
            if dm_message and winners:
                for winner in winners:
                    try:
                        embed = discord.Embed(
                            title="🎉 You won a giveaway!",
                            description=f"You won **{giveaway_data['prize']}** in {channel.guild.name}!",
                            color=discord.Color.gold()
                        )
                        embed.add_field(name="Prize Details", value=dm_message, inline=False)
                        embed.set_footer(text=f"Giveaway ID: {giveaway_id}")
                        await winner.send(embed=embed)
                    except Exception as e:
                        print(f"Error sending DM to winner: {e}")

            for winner in winners:
                update_user_statistics(channel.guild.id, winner.id, "wins", 1)

            for participant_id in participants:
                if participant_id not in winner_ids:
                    update_user_statistics(channel.guild.id, participant_id, "losses", 1)

            embed = message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "🎉 **GIVEAWAY ENDED** 🎉"

            new_fields = []
            for field in embed.fields:
                if field.name != "Participants":
                    new_fields.append(field)

            embed.clear_fields()
            for field in new_fields:
                embed.add_field(name=field.name, value=field.value, inline=field.inline)

            embed.add_field(name="Winners", value=winners_text, inline=False)
            embed.add_field(name="Total Participants", value=str(len(participants)), inline=True)

            await message.edit(embed=embed, view=view)

            announcement = f"🎉 **CONGRATULATIONS!** 🎉\n"
            announcement += f"The winners of **{giveaway_data['prize']}** (ID: `{giveaway_id}`) are: {winners_text}!\n"
            announcement += f"A total of **{len(participants)}** members participated in the giveaway!"

            if winner_role_id:
                role = channel.guild.get_role(winner_role_id)
                if role:
                    announcement += f"\n🏆 Winners received the {role.mention} role!"

            await channel.send(announcement)

        await log_to_audit_channel(giveaway_data['guild_id'],
                                 f"🎉 Giveaway ended: **{giveaway_data['prize']}** with {len(participants)} participants (ID: {giveaway_id})")

        if giveaway_id in active_giveaways:
            del active_giveaways[giveaway_id]
        remove_giveaway_from_file(giveaway_id)

    except discord.NotFound:
        print(f"Giveaway message not found: {giveaway_id}")
        if giveaway_id in active_giveaways:
            del active_giveaways[giveaway_id]
        remove_giveaway_from_file(giveaway_id)
    except Exception as e:
        print(f"Error ending giveaway: {e}")


# Event for button interactions
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get('custom_id', '').startswith('leave_'):
            giveaway_id = interaction.data['custom_id'][5:]

            giveaway_data = None
            for gid, data in active_giveaways.items():
                if gid == giveaway_id and data['guild_id'] == interaction.guild.id:
                    giveaway_data = data
                    break

            if not giveaway_data:
                await interaction.response.send_message(
                    "❌ This giveaway no longer exists! It might have ended or been cancelled.", ephemeral=True)
                return

            view = giveaway_data['view']

            if interaction.user.id not in view.participants:
                await interaction.response.send_message("❌ You are not participating in this giveaway!", ephemeral=True)
                return

            view.participants.remove(interaction.user.id)
            await update_participant_count(giveaway_id)
            save_giveaways()

            await interaction.response.send_message(f"✅ You have left the giveaway **{giveaway_data['prize']}**!",
                                                    ephemeral=True)
            await log_to_audit_channel(interaction.guild.id,
                                     f"🚪 {interaction.user.mention} left giveaway: **{giveaway_data['prize']}** (ID: {giveaway_id})")
            return

        for giveaway_id, giveaway_data in active_giveaways.items():
            if giveaway_data['view'] is not None:
                if interaction.data.get('custom_id') in ["join_giveaway", "show_participants"]:
                    if interaction.data.get('custom_id') == "join_giveaway":
                        await update_participant_count(giveaway_id)
                        save_giveaways()
                    break


# Start bot with environment variable
if __name__ == "__main__":
    # Get token from environment variable
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable is not set!")
        print("Please set the environment variable:")
        print("  On Linux/Mac: export DISCORD_BOT_TOKEN='your_token_here'")
        print("  On Windows: set DISCORD_BOT_TOKEN=your_token_here")
        print("  In Docker: Use -e DISCORD_BOT_TOKEN='your_token_here'")
        exit(1)
    
    print("✅ Starting bot with environment variable token...")
    bot.run(TOKEN)
import discord

class GameInteractionProxy:
    def __init__(self, original_interaction: discord.Interaction):
        self._og = original_interaction
        self._target_message = None
        
        self.response = ResponseProxy(self)
        self.followup = FollowupProxy(self)

    def __getattr__(self, name):
        return getattr(self._og, name)

    async def edit_original_response(self, **kwargs):
        if not self._target_message:
            # First time updating visual! Instead of editing old game, we spawn a new message!
            kwargs['wait'] = True
            msg = await self._og.followup.send(**kwargs)
            self._target_message = msg
            return msg
        else:
            try:
                return await self._target_message.edit(**kwargs)
            except discord.NotFound:
                pass
        return await self._og.edit_original_response(**kwargs)

class ResponseProxy:
    def __init__(self, proxy: "GameInteractionProxy"):
        self._proxy = proxy
        self._og_response = proxy._og.response

    def __getattr__(self, name):
        return getattr(self._og_response, name)

    async def defer(self, **kwargs):
        return await self._og_response.defer(**kwargs)

class FollowupProxy:
    def __init__(self, proxy: "GameInteractionProxy"):
        self._proxy = proxy
        self._og_followup = proxy._og.followup

    def __getattr__(self, name):
        return getattr(self._og_followup, name)

    async def send(self, **kwargs):
        kwargs['wait'] = True
        msg = await self._og_followup.send(**kwargs)
        self._proxy._target_message = msg
        return msg

class PlayAgainView(discord.ui.View):
    def __init__(self, command_callback, cog, _old_interaction, *args, **kwargs):
        super().__init__(timeout=None)
        self.command_callback = command_callback
        self.cog = cog
        self.args = args
        self.kwargs = kwargs

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.primary, emoji="🔄")
    async def play_again_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
            
        try:
            # Edit the message directly to disable the button WITHOUT consuming the interaction response
            await interaction.message.edit(view=self)
        except Exception:
            pass
            
        proxy = GameInteractionProxy(interaction)
        try:
            await self.command_callback(self.cog, proxy, *self.args, **self.kwargs)
        except Exception as e:
            print(f"[PLAY AGAIN] Error inside callback: {e}")

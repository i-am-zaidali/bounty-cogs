import datetime
import typing
from io import BytesIO

import discord
import matplotlib.pyplot as plt
import numpy as np
import pandas
from matplotlib.patches import Patch
from redbot.core.utils.chat_formatting import humanize_list

from ..common.models import DAYS
from ..common.utils import dates_iter

if typing.TYPE_CHECKING:
    from ..main import TimeSlots


class TimeSlotsGenerator:
    def __init__(self, cog: "TimeSlots", guild: discord.Guild):
        self.cog = cog
        self.bot = cog.bot
        self.guild = guild
        self.conf = cog.db.get_conf(guild.id)

    def get_user_color(self, uid: int) -> tuple[float, float, float]:
        return self.conf.get_user(uid).color

    @staticmethod
    def get_merged_color(
        *colors: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        if not colors:
            return (1, 1, 1)  # Default to white if no colors are provided
        blended_color = np.mean(colors, axis=0)  # Average the RGB values
        return tuple(blended_color)

    @staticmethod
    def color_string_to_tuple(color_string: str) -> tuple[float, float, float]:
        if isinstance(color_string, tuple) and len(color_string) == 3:
            return color_string
        if color_string.count(",") != 2:
            raise ValueError(f"Invalid color string: {color_string}")
        return tuple(map(float, color_string.split(",")))

    @staticmethod
    def color_tuple_to_string(color: tuple[float, float, float]) -> str:
        return ",".join(map(str, color))

    def color_chart(
        self,
        time_chart: pandas.DataFrame,
        color_chart: pandas.DataFrame,
        user_timeslots: dict[int, dict[DAYS, list[int]]],
        day_to_date: dict[DAYS, str],
    ):
        user_colors: dict[tuple[str], tuple[float, float, float]] = {}
        for uid, timeslots in user_timeslots.items():
            user = self.guild.get_member(uid)
            if not user:
                continue
            for day, times in timeslots.items():
                day = day_to_date[day]
                for time in times:
                    ftime = f"{time:02d}:00"
                    ccat = color_chart.at[ftime, day]
                    if ccat != "1,1,1":
                        color = self.get_merged_color(
                            self.color_string_to_tuple(ccat),
                            self.color_string_to_tuple(self.get_user_color(uid)),
                        )
                        color_chart.at[ftime, day] = self.color_tuple_to_string(color)
                        time_chart.at[ftime, day] += f"\n{user.display_name}"
                        listed_users: list[str] = time_chart.at[ftime, day].split("\n")
                        user_colors[tuple(listed_users)] = color

                    else:
                        color = user_colors[(user.display_name,)] = self.get_user_color(
                            uid
                        )
                        color_chart.at[ftime, day] = self.color_tuple_to_string(color)
                        time_chart.at[ftime, day] = user.display_name

        return user_colors

    def visualize_time_chart(
        self,
        time_chart: pandas.DataFrame,
        color_chart: pandas.DataFrame,
        user_colors: dict[tuple[str], tuple[float, float, float]],
    ):
        fig, ax = plt.subplots(figsize=(10, 15))
        ax.axis("off")  # Hide the axes

        row_heights = [
            0.025
            * max(
                cell.count("\n") + 1 for cell in time_chart.loc[row]
            )  # Count lines in each cell
            for row in time_chart.index
        ]

        # Create the table
        table = ax.table(
            cellText=time_chart.values,
            rowLabels=time_chart.index,
            colLabels=time_chart.columns,
            loc="center",
            cellColours=[
                [
                    self.color_string_to_tuple(color_chart.at[row, col])
                    for col in color_chart.columns
                ]
                for row in color_chart.index
            ],
        )

        for i, row_height in enumerate(row_heights, 1):
            table._cells[(i, -1)].set_height(row_height)  # Adjust height for row labels
            for j in range(len(time_chart.columns)):
                if i == 1:
                    table._cells[(i - 1, j)].set_height(0.03)
                table._cells[(i, j)].set_height(row_height)  # Adjust cell heights

        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.auto_set_column_width(col=list(range(len(color_chart.columns))))
        table.scale(2.5, 1)

        legend_handles = [
            Patch(
                facecolor=self.color_string_to_tuple(color),
                edgecolor="black",
                label=humanize_list(users),
            )
            for users, color in user_colors.items()
        ]

        if user_colors:
            fig.legend(
                handles=legend_handles,
                loc="lower center",
                bbox_to_anchor=(0.5, -0.1),
                ncol=2,
                fontsize=12,
            )

        fig.tight_layout(rect=[0, 0.03, 1, 0.95])
        io = BytesIO()
        fig.savefig(io, bbox_inches="tight")
        io.seek(0)
        return io

    @staticmethod
    def get_blank_chart(fillvalue):
        return pandas.DataFrame(
            index=[f"{hour:02d}:00" for hour in range(24)],
            columns=[day.name.title() for day in DAYS],
        ).fillna(fillvalue)

    def get_colored_organized_chart(
        self, user_timeslots: dict[int, dict[DAYS, list[int]]]
    ):
        assert self.conf.next_chart_reset is not None
        colour_chart = self.get_blank_chart("1,1,1")
        time_chart = self.get_blank_chart("■" * 11)
        user_colors = {}
        day_to_date = {
            DAYS(date.weekday()): date.strftime("%A\n%m/%d/%Y")
            for date in dates_iter(
                self.conf.next_chart_reset - datetime.timedelta(days=6),
                self.conf.next_chart_reset,
            )
        }
        colour_chart.columns = time_chart.columns = list(day_to_date.values())
        if user_timeslots:
            user_colors = self.color_chart(
                time_chart=time_chart,
                color_chart=colour_chart,
                user_timeslots=user_timeslots,
                day_to_date=day_to_date,
            )
        return self.visualize_time_chart(
            time_chart=time_chart, color_chart=colour_chart, user_colors=user_colors
        )

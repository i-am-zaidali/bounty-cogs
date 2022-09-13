import typing
from enum import Enum


class Category(Enum):
    TANK = "Tank"
    MELEE = "Melee"
    RANGED = "Ranged"
    HEALER = "Healer"

    @property
    def emoji(self):
        return {
            "Tank": "<:tank:975467387203764246> ",  # emoji edits here just edit the strings
            "Healer": "<:healer:975467387073728563> ",
            "Melee": "<:melee:975467387535118406> ",
            "Ranged": "<:ranged:975467387505750116>",
        }[self.value]


class_spec_dict: typing.Dict[
    str,
    typing.Union[
        str, typing.Dict[str, typing.Dict[str, typing.Union[typing.Tuple[Category], str]]]
    ],
] = {
    "Death Knight": {
        "emoji": "<:deahthknight:975436654154219550>",  # emoji edit here
        "specs": {
            "Blood": {
                "categories": (
                    Category.TANK,
                    Category.MELEE,
                ),
                "emoji": "<:blood:975436654322008064>",  # emoji edit here
            },
            "Frost": {
                "categories": (
                    Category.MELEE,
                ),
                "emoji": "<:dfrost:975462630582022256>",  # emoji edit here
            },
            "Unholy": {
                "categories": (
                    Category.MELEE,
                ),
                "emoji": "<:unholy:975436654108082226>",  # emoji edit here
            },
        }
        # you know everywhere else to edit the emojis below
    },
    "Druid": {
        "emoji": "<:druid:975448972472770570> ",
        "specs": {
            "Balance": {
                "categories": (Category.RANGED,),
                "emoji": "<:balance:975436654091329576>",
            },
            "Feral": {"categories": (Category.MELEE,), "emoji": "<:feral:975436654246518845>"},
            "Feral (tank)": {
                "categories": (Category.TANK,),
                "emoji": "<:feral:975436654246518845>",
            },
            "Restoration": {
                "categories": (Category.HEALER,),
                "emoji": "<:resto:975436653910962237>",
            },
        },
    },
    "Hunter": {
        "emoji": "<:hunter:975448994350252032> ",
        "specs": {
            "Beast Mastery": {
                "categories": (Category.RANGED,),
                "emoji": "<:beastmaster:975436654233927700>",
            },
            "Marksmanship": {
                "categories": (Category.RANGED,),
                "emoji": "<:marksman:975436654061977630>",
            },
            "Survival": {
                "categories": (Category.RANGED,),
                "emoji": "<:survival:975436654116487178>",
            },
        },
    },
    "Mage": {
        "emoji": "<:mage:975449007079964722>",
        "specs": {
            "Arcane": {"categories": (Category.RANGED,), "emoji": "<:arcane:975436653890002977>"},
            "Fire": {"categories": (Category.RANGED,), "emoji": "<:fire:975436653688668191>"},
            "Frost": {"categories": (Category.RANGED,), "emoji": "<:frost:975436654070337556>"},
        },
    },
    "Paladin": {
        "emoji": "<:paladin:975449019469955152> ",
        "specs": {
            "Holy": {"categories": (Category.HEALER,), "emoji": "<:holy:975436654007423126>"},
            "Protection": {"categories": (Category.TANK,), "emoji": "<:prot:975436654028411010>"},
            "Retribution": {"categories": (Category.MELEE,), "emoji": "<:ret:975436654049366116>"},
        },
    },
    "Priest": {
        "emoji": "<:priest:975449029360111686> ",
        "specs": {
            "Discipline": {
                "categories": (Category.HEALER,),
                "emoji": "<:disc:975436653994856508>",
            },
            "Holy": {"categories": (Category.HEALER,), "emoji": "<:holy:975436654007423126>"},
            "Shadow": {"categories": (Category.RANGED,), "emoji": "<:shadow:975436653978058792>"},
        },
    },
    "Rogue": {
        "emoji": "<:rogue:975449040227553360> ",
        "specs": {
            "Assassination": {
                "categories": (Category.MELEE,),
                "emoji": "<:assassination:975436653973893180>",
            },
            "Combat": {"categories": (Category.MELEE,), "emoji": "<:combat:975436654498181131>"},
            "Subtlety": {"categories": (Category.MELEE,), "emoji": "<:sub:975436653936128121>"},
        },
    },
    "Shaman": {
        "emoji": "<:shaman:975449050453278790>",
        "specs": {
            "Elemental": {
                "categories": (Category.RANGED,),
                "emoji": "<:elemental:975436653919363092>",
            },
            "Enhancement": {
                "categories": (Category.MELEE,),
                "emoji": "<:enhance:975436653990670406>",
            },
            "Restoration": {
                "categories": (Category.HEALER,),
                "emoji": "<:resto:975436653910962237>",
            },
        },
    },
    "Warlock": {
        "emoji": "<:warlock:975449059609440367>",
        "specs": {
            "Affliction": {
                "categories": (Category.RANGED,),
                "emoji": "<:affliction:975436654070358056> ",
            },
            "Demonology": {
                "categories": (Category.RANGED,),
                "emoji": "<:demon:975436653969694740>",
            },
            "Destruction": {
                "categories": (Category.RANGED,),
                "emoji": "<:destro:975436653944504380>",
            },
        },
    },
    "Warrior": {
        "emoji": "<:warrior:975449085073047572>",
        "specs": {
            "Arms": {"categories": (Category.MELEE,), "emoji": "<:arms:975436653894185100>"},
            "Fury": {"categories": (Category.MELEE,), "emoji": "<:fury:975436653869010954>"},
            "Protection": {"categories": (Category.TANK,), "emoji": "<:wprot:975469853370638406>"},
        },
    },
}

emoji_class_dict = {
    "<:deahthknight:975436654154219550>": "Death Knight",
    "<:druid:975448972472770570>": "Druid",
    "<:hunter:975448994350252032>": "Hunter",
    "<:mage:975449007079964722>": "Mage",
    "<:paladin:975449019469955152>": "Paladin",
    "<:priest:975449029360111686>": "Priest",
    "<:rogue:975449040227553360>": "Rogue",
    "<:shaman:975449050453278790>": "Shaman",
    "<:warlock:975449059609440367>": "Warlock",
    "<:warrior:975449085073047572>": "Warrior",
}


# specs = {
#     'Blood': ('Tank', 'Melee', ),
#     'Frost': ('Tank', 'Ranged', 'Melee', ),
#     'Unholy': ('Tank', 'Melee', ),
#     'Feral': ('Tank', 'Melee', ),
#     'Protection': ('Tank', ),
#     'Arcane': ('Ranged', ),
#     'Fire': ('Ranged', ),
#     'Elemental': ('Ranged', ),
#     'Balance': ('Ranged', ),
#     'Affliction': ('Ranged', ),
#     'Demonology': ('Ranged', ),
#     'Destruction': ('Ranged', ),
#     'Beast Mastery': ('Ranged', ),
#     'Marksmanship': ('Ranged', ),
#     'Survival': ('Ranged', ),
#     'Shadow': ('Ranged', ),
#     'Assassination': ('Melee', ),
#     'Outlaw': ('Melee', ),
#     'Subtlety': ('Melee', ),
#     'Enhancement': ('Melee', ),
#     'Retribution': ('Melee', ),
#     'Arms': ('Melee', ),
#     'Fury': ('Melee', ),
#     'Restoration': ('Healer', ),
#     'Holy': ('Healer', ),
#     'Discipline': ('Healer', )
# }

# spec_cat_pair = {
#     'Blood': ('Tank', 'Melee', ),
#     'Frost': ('Tank', 'Ranged', 'Melee', ),
#     'Unholy': ('Tank', 'Melee', ),
#     'Feral': ('Tank', 'Melee', ),
#     'Protection': ('Tank', ),
#     'Arcane': ('Ranged', ),
#     'Fire': ('Ranged', ),
#     'Elemental': ('Ranged', ),
#     'Balance': ('Ranged', ),
#     'Affliction': ('Ranged', ),
#     'Demonology': ('Ranged', ),
#     'Destruction': ('Ranged', ),
#     'Beast Mastery': ('Ranged', ),
#     'Marksmanship': ('Ranged', ),
#     'Survival': ('Ranged', ),
#     'Shadow': ('Ranged', ),
#     'Assassination': ('Melee', ),
#     'Outlaw': ('Melee', ),
#     'Subtlety': ('Melee', ),
#     'Enhancement': ('Melee', ),
#     'Retribution': ('Melee', ),
#     'Arms': ('Melee', ),
#     'Fury': ('Melee', ),
#     'Restoration': ('Healer', ),
#     'Holy': ('Healer', ),
#     'Discipline': ('Healer', )
# }

# cat_spec_pair = {
#     'Healer': ['Restoration', 'Holy', 'Discipline'],
#     'Melee': [
#         'Blood',
#         'Frost',
#         'Unholy',
#         'Feral',
#         'Assassination',
#         'Outlaw',
#         'Subtlety',
#         'Enhancement',
#         'Retribution',
#         'Arms',
#         'Fury'
#     ],
#     'Ranged': [
#         'Arcane',
#         'Fire',
#         'Frost',
#         'Elemental',
#         'Balance',
#         'Affliction',
#         'Demonology',
#         'Destruction',
#         'Beast Mastery',
#         'Marksmanship',
#         'Survival',
#         'Shadow'
#     ],
#     'Tank': ['Blood', 'Frost', 'Unholy', 'Feral', 'Protection']
# }

# class_spec_pair = {
#     'Death Knight': ['Blood', 'Frost', 'Unholy'],
#     'Druid': ['Balance', 'Feral', 'Restoration'],
#     'Hunter': ['Beast Mastery', 'Marksmanship', 'Survival'],
#     'Mage': ['Arcane', 'Fire', 'Frost'],
#     'Paladin': ['Holy', 'Protection', 'Retribution'],
#     'Priest': ['Discipline', 'Holy', 'Shadow'],
#     'Rogue': ['Assassination', 'Outlaw', 'Subtlety'],
#     'Shaman': ['Elemental', 'Enhancement', 'Restoration'],
#     'Warlock': ['Affliction', 'Demonology', 'Destruction'],
#     'Warrior': ['Arms', 'Fury', 'Protection']
# }

# spec_class_pair = {
#     'Affliction': ['Warlock'],
#     'Arcane': ['Mage'],
#     'Arms': ['Warrior'],
#     'Assassination': ['Rogue'],
#     'Balance': ['Druid'],
#     'Beast Mastery': ['Hunter'],
#     'Blood': ['Death Knight'],
#     'Demonology': ['Warlock'],
#     'Destruction': ['Warlock'],
#     'Discipline': ['Priest'],
#     'Elemental': ['Shaman'],
#     'Enhancement': ['Shaman'],
#     'Feral': ['Druid'],
#     'Fire': ['Mage'],
#     'Frost': ['Death Knight', 'Mage'],
#     'Fury': ['Warrior'],
#     'Holy': ['Paladin', 'Priest'],
#     'Marksmanship': ['Hunter'],
#     'Outlaw': ['Rogue'],
#     'Protection': ['Paladin', 'Warrior'],
#     'Restoration': ['Druid', 'Shaman'],
#     'Retribution': ['Paladin'],
#     'Shadow': ['Priest'],
#     'Subtlety': ['Rogue'],
#     'Survival': ['Hunter'],
#     'Unholy': ['Death Knight']
# }

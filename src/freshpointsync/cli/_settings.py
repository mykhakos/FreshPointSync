import argparse
import json
import os
import typing


class DefaultSettings:
    LAST_LOCATION: typing.Optional[int] = None
    DEFAULT_QUERY: dict[str, typing.Any] = {'available': True}

    @classmethod
    def get(cls) -> dict[str, typing.Any]:
        return {
            QuerySettings.KEY_LAST_LOCATION: cls.LAST_LOCATION,
            QuerySettings.KEY_DEFAULT_QUERY: cls.DEFAULT_QUERY
            }


class QuerySettings:
    KEY_DEFAULT_QUERY = 'default_query'
    KEY_LAST_LOCATION = 'last_location'
    ARGNAME_DEFAULT = 'default'
    ARGNAME_LOCATION = 'positional_location'
    ARGNAME_LOCATION_ALT = 'location'

    def __init__(self, settings: dict) -> None:
        self._settings = self.validate_settings_dict(settings)

    @classmethod
    def from_file(cls, filepath: str) -> 'QuerySettings':
        if not os.path.exists(filepath):
            data = DefaultSettings.get()
            with open(filepath, 'w', encoding='utf-8') as file:
                json.dump(data, file)
        else:
            with open(filepath, 'r', encoding='utf-8') as file:
                data = json.load(file)
        return cls(data)

    @classmethod
    def validate_settings_dict(cls, settings: dict) -> dict[str, typing.Any]:
        if cls.KEY_LAST_LOCATION not in settings:
            settings[cls.KEY_LAST_LOCATION] = DefaultSettings.LAST_LOCATION
        if cls.KEY_DEFAULT_QUERY not in settings:
            settings[cls.KEY_DEFAULT_QUERY] = DefaultSettings.DEFAULT_QUERY
        return settings

    def get_default_query(self) -> argparse.Namespace:
        default_query = self._settings.get(self.KEY_DEFAULT_QUERY, {})
        return argparse.Namespace(**default_query)

    def set_default_query(self, args: argparse.Namespace) -> None:
        args_dict = vars(args)
        for arg in (
            self.ARGNAME_DEFAULT,
            self.ARGNAME_LOCATION,
            self.ARGNAME_LOCATION_ALT
        ):
            if arg in args_dict:
                del args_dict[arg]
        self._settings[self.KEY_DEFAULT_QUERY] = args_dict

    def get_last_location(self) -> typing.Optional[int]:
        return self._settings.get(self.KEY_LAST_LOCATION)

    def set_last_location(self, location_id: typing.Union[int, str]) -> None:
        self._settings[self.KEY_LAST_LOCATION] = int(location_id)

    def to_file(self, filepath: str) -> None:
        with open(filepath, 'w', encoding='utf-8') as file:
            json.dump(self._settings, file, indent=4)

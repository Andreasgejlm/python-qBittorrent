# Built-in Imports
import json
from typing import Optional
from time import sleep

# 3rd Party Imports
import requests

# Local Imports
from qbittorrent.Exceptions import WrongCredentials


class Client:
    """Class to interact with qBittorrent WEB API"""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        verify: bool = True,
        timeout: bool = None,
        max_attempts_on_403: int = 3,
    ):
        """
        Initialize the client

        :param url: Base URL of the qBittorrent WEB API
        :param username: Username to use for login
        :param password: Password to use for login
        :param verify: Boolean to specify if SSL verification should be done.
                       Defaults to True.
        :param timeout: How many seconds to wait for the server to send data before giving up, as a float,
                        or a `(connect timeout, read timeout)` tuple.
                        Defaults to None.
        :param max_attempts_on_403: Maximum time a request will be done after a 403 and a re-login before
                                    raising HTTPError
        """
        self._username = username
        self._password = password

        if not url.endswith("/"):
            url += "/"

        self._url = url + "api/v2/"
        self._verify = verify
        self._timeout = timeout

        self._max_attempts_on_403 = max_attempts_on_403

        self._session = None
        self._is_authenticated = False

        # Create session & login
        self.login()

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str):
        """
        Updates the username and attempts to re-login

        :param value:
        :raises WrongCredentials: If the username & password combination are wrong
        :return:
        """
        self._username = value
        self.login()

    @property
    def password(self) -> str:
        return self._password

    @password.setter
    def password(self, value: str):
        """
        Updates the password and attempts to re-login

        :param value:
        :raises WrongCredentials: If the username & password combination are wrong
        :return:
        """
        self._password = value
        self.login()

    @property
    def qbittorrent_version(self):
        """
        Get qBittorrent version.
        """
        return self._get("app/version")

    @property
    def api_version(self):
        """
        Get WEB API version.
        """
        return self._get("app/webapiVersion")

    def update_credentials(self, username: str, password: str):
        """
        In case you need to update both username and password you can use this function instead of the property
        setters. It will attempt to log in after changes are made.

        This should avoid raising WrongCredentials when both credentials change.

        :param username:
        :param password:
        :raises WrongCredentials: If the username & password combination are wrong
        :return:
        """
        self._username = username
        self._password = password
        self.login()

    def _get(self, endpoint, **kwargs):
        """
        Method to perform GET request on the API.

        :param endpoint: Endpoint of the API.
        :param kwargs: Other keyword arguments for requests.

        :return: Response of the GET request.
        """
        return self._request(endpoint, "get", **kwargs)

    def _post(self, endpoint, data, **kwargs):
        """
        Method to perform POST request on the API.

        :param endpoint: Endpoint of the API.
        :param data: POST DATA for the request.
        :param kwargs: Other keyword arguments for requests.

        :return: Response of the POST request.
        """
        return self._request(endpoint, "post", data, **kwargs)

    def _request(self, endpoint, method, data=None, attempt: int = 0, **kwargs):
        """
        Method to handle both GET and POST requests.

        :param endpoint: Endpoint of the API.
        :param method: Method of HTTP request.
        :param data: POST DATA for the request.
        :param attempt: Attempts to retry this request after 403 and login
                        Used to limit the amount of retries
        :param kwargs: Other keyword arguments. Passed down to request

        :return: Response for the request.
        """
        final_url = self._url + endpoint

        kwargs["verify"] = self._verify
        kwargs["timeout"] = self._timeout
        if method == "get":
            request = self._session.get(final_url, **kwargs)
        else:
            request = self._session.post(final_url, data, **kwargs)

        if request.status_code == 403 and attempt <= self._max_attempts_on_403:
            self.login()
            return self._request(endpoint, method, data, attempt=attempt + 1, **kwargs)

        request.raise_for_status()
        request.encoding = "utf_8"

        if len(request.text) == 0:
            return json.loads("{}")

        try:
            data = json.loads(request.text)
        except ValueError:
            data = request.text

        return data

    def login(self):
        """
        Method to authenticate the qBittorrent Client.

        Declares a class attribute named ``session`` which
        stores the authenticated session if the login is correct.
        Else, shows the login error.

        :raises WrongCredentials: When given credentials are wrong
        :return:
        """
        self._session = requests.Session()

        login = self._session.post(
            self._url + "auth/login",
            data={"username": self.username, "password": self.password},
            verify=self._verify,
        )
        if login.text == "Ok.":
            return

        raise WrongCredentials

    def logout(self) -> Optional[requests.Response]:
        """
        Logout the current session.
        """
        response = self._get("auth/logout")
        return response

    def shutdown(self):
        """
        Shutdown qBittorrent.
        """
        return self._get("app/shutdown")

    def get_default_save_path(self):
        """
        Get default save path.
        """
        return self._get("app/defaultSavePath")

    def get_log(self, **params):
        """
        Returns a list of log entries matching the supplied params.

        :param normal: Include normal messages (default: true).
        :param info: Include info messages (default: true).
        :param warning: Include warning messages (default: true).
        :param critical: Include critical messages (default: true).
        :param last_known_id: Exclude messages with "message id" <= last_known_id (default: -1).

        :return: list().
        For example: qb.get_log(normal='true', info='true')
        """
        return self._get("log/main", params=params)

    def torrents(self, **filters):
        """
        Returns a list of torrents matching the supplied filters.

        :param filter: Current status of the torrents.
        :param category: Fetch all torrents with the supplied label.
        :param sort: Sort torrents by.
        :param reverse: Enable reverse sorting.
        :param limit: Limit the number of torrents returned.
        :param offset: Set offset (if less than 0, offset from end).

        :return: list() of torrent with matching filter.
        For example: qb.torrents(filter='downloading', sort='ratio').
        """
        params = {}
        for name, value in filters.items():
            # make sure that old 'status' argument still works
            name = "filter" if name == "status" else name
            params[name] = value

        return self._get("torrents/info", params=params)

    def get_torrent(self, infohash):
        """
        Get details of the torrent.

        :param infohash: INFO HASH of the torrent.
        """
        return self._get("torrents/properties?hash=" + infohash.lower())

    def get_torrent_trackers(self, infohash):
        """
        Get trackers for the torrent.

        :param infohash: INFO HASH of the torrent.
        """
        return self._get("torrents/trackers?hash=" + infohash.lower())

    def get_torrent_webseeds(self, infohash):
        """
        Get webseeds for the torrent.

        :param infohash: INFO HASH of the torrent.
        """
        return self._get("torrents/webseeds?hash=" + infohash.lower())

    def get_torrent_files(self, infohash):
        """
        Get list of files for the torrent.

        :param infohash: INFO HASH of the torrent.
        """
        return self._get("torrents/files?hash=" + infohash.lower())

    def get_torrent_piece_states(self, infohash):
        """
        Get list of all pieces (in order) of a specific torrent.

        :param infohash: INFO HASH of the torrent.
        :return: array of states (integers).
        """
        return self._get("torrents/pieceStates?hash=" + infohash.lower())

    def get_torrent_piece_hashes(self, infohash):
        """
        Get list of all hashes (in order) of a specific torrent.

        :param infohash: INFO HASH of the torrent.
        :return: array of hashes (strings).
        """
        return self._get("torrents/pieceHashes?hash=" + infohash.lower())

    @property
    def global_transfer_info(self):
        """
        :return: dict{} of the global transfer info of qBittorrent.

        """
        return self._get("transfer/info")

    @property
    def preferences(self):
        """
        Get the current qBittorrent preferences.
        Can also be used to assign individual preferences.
        For setting multiple preferences at once,
        see ``set_preferences`` method.

        Note: Even if this is a ``property``,
        to fetch the current preferences' dict, you are required
        to call it like a bound method.

        Wrong::

            qb.preferences

        Right::

            qb.preferences()

        """
        prefs = self._get("app/preferences")

        class Proxy(Client):
            """
            Proxy class to allow assignment of individual preferences.
            this class overrides some methods to ease things.

            Because of this, settings can be assigned like::

                In [5]: prefs = qb.preferences()

                In [6]: prefs['autorun_enabled']
                Out[6]: True

                In [7]: prefs['autorun_enabled'] = False

                In [8]: prefs['autorun_enabled']
                Out[8]: False

            """

            def __init__(self, url, prefs, auth, session):
                self.url = url
                self.prefs = prefs
                self._is_authenticated = auth
                self.session = session

            def __getitem__(self, key):
                return self.prefs[key]

            def __setitem__(self, key, value):
                kwargs = {key: value}
                return self.set_preferences(**kwargs)

            def __call__(self):
                return self.prefs

        return Proxy(self._url, prefs, self._is_authenticated, self._session)

    def sync_main_data(self, rid=0):
        """
        Sync the torrents main data by supplied LAST RESPONSE ID.
        Read more @ https://git.io/fxgB8

        :param rid: Response ID of last request.
        """
        return self._get("sync/maindata", params={"rid": rid})

    def sync_peers_data(self, infohash, rid=0):
        """
        Sync the torrent peers data by supplied LAST RESPONSE ID.
        Read more @ https://git.io/fxgBg

        :param infohash: INFO HASH of torrent.
        :param rid: Response ID of last request.
        """
        params = {"hash": infohash.lower(), "rid": rid}
        return self._get("sync/torrentPeers", params=params)

    def download_from_link(self, link, **kwargs):
        """
        Download torrent using a link.

        :param link: URL Link or list of.
        :param savepath: Path to download the torrent.
        :param category: Label or Category of the torrent(s).

        :return: Empty JSON data.
        """
        # old:new format
        old_arg_map = {"save_path": "savepath"}  # , 'label': 'category'}

        # convert old option names to new option names
        options = kwargs.copy()
        for old_arg, new_arg in old_arg_map.items():
            if options.get(old_arg) and not options.get(new_arg):
                options[new_arg] = options[old_arg]

        if isinstance(link, list):
            options["urls"] = "\n".join(link)
        else:
            options["urls"] = link

        # workaround to send multipart/formdata request
        # http://stackoverflow.com/a/23131823/4726598
        dummy_file = {"_dummy": (None, "_dummy")}

        return self._post("torrents/add", data=options, files=dummy_file)

    def download_from_file(self, file_buffer, **kwargs):
        """
        Download torrent using a file.

        :param file_buffer: Single file() buffer or list of.
        :param save_path: Path to download the torrent.
        :param label: Label of the torrent(s).

        :return: Empty JSON data.
        """
        if isinstance(file_buffer, list):
            torrent_files = {}
            for i, f in enumerate(file_buffer):
                torrent_files.update({"torrents%s" % i: f})
        else:
            torrent_files = {"torrents": file_buffer}

        data = kwargs.copy()

        if data.get("save_path"):
            data.update({"savepath": data["save_path"]})
        return self._post("torrents/add", data=data, files=torrent_files)

    def add_trackers(self, infohash, trackers):
        """
        Add trackers to a torrent.

        :param infohash: INFO HASH of torrent.
        :param trackers: Trackers.
        :note %0A (aka LF newline) between trackers. Ampersand in tracker urls MUST be escaped.
        """
        data = {"hash": infohash.lower(), "urls": trackers}
        return self._post("torrents/addTrackers", data=data)

    def set_torrent_location(self, infohash_list, location):
        """
        Set the location for the torrent

        :param infohash: INFO HASH of torrent.
        :param location: /mnt/nfs/media.
        """
        data = self._process_infohash_list(infohash_list)
        data["location"] = location
        return self._post("torrents/setLocation", data=data)

    def set_torrent_name(self, infohash, name):
        """
        Set the name for the torrent

        :param infohash: INFO HASH of torrent.
        :param name: Whatever_name_you_want.
        """
        data = {"hash": infohash.lower(), "name": name}
        return self._post("torrents/rename", data=data)

    @staticmethod
    def _process_infohash_list(infohash_list):
        """
        Method to convert the infohash_list to qBittorrent API friendly values.

        :param infohash_list: List of infohash.
        """
        if isinstance(infohash_list, list):
            data = {"hashes": "|".join([h.lower() for h in infohash_list])}
        else:
            data = {"hashes": infohash_list.lower()}
        return data

    def pause(self, infohash):
        """
        Pause a torrent.

        :param infohash: INFO HASH of torrent.
        """
        return self._post("torrents/pause", data={"hashes": infohash.lower()})

    def pause_all(self):
        """
        Pause all torrents.
        """
        return self._post("torrents/pause", data={"hashes": "all"})

    def pause_multiple(self, infohash_list):
        """
        Pause multiple torrents.

        :param infohash_list: Single or list() of infohashes.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/pause", data=data)

    def set_category(self, infohash_list, category):
        """
        Set the category on multiple torrents.

        The category must exist before using set_category. As of v2.1.0,the API
        returns a 409 Client Error for any valid category name that doesn't
        already exist.

        :param infohash_list: Single or list() of infohashes.
        :param category: If category is set to empty string '',
        the torrent(s) specified is/are removed from all categories.
        """
        data = self._process_infohash_list(infohash_list)
        data["category"] = category
        return self._post("torrents/setCategory", data=data)

    def create_category(self, category):
        """
        Create a new category
        :param category: category to create
        """
        return self._post("torrents/createCategory", data={"category": category.lower()})

    def remove_category(self, categories):
        """
        Remove categories

        :param categories: can contain multiple cateogies separated by \n (%0A urlencoded).
        """

        return self._post("torrents/removeCategories", data={"categories": categories})

    def resume(self, infohash):
        """
        Resume a paused torrent.

        :param infohash: INFO HASH of torrent.
        """
        return self._post("torrents/resume", data={"hashes": infohash.lower()})

    def resume_all(self):
        """
        Resume all torrents.
        """
        return self._post("torrents/resume", data={"hashes": "all"})

    def resume_multiple(self, infohash_list):
        """
        Resume multiple paused torrents.

        :param infohash_list: Single or list() of infohashes.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/resume", data=data)

    def delete(self, infohash_list):
        """
        Delete torrents. Does not remove files.

        :param infohash_list: Single or list() of infohashes.
        """
        return self._delete(infohash_list)

    def delete_all(self):
        """
        Delete all torrents. Does not remove files.
        """
        return self._delete("all")

    def delete_permanently(self, infohash_list):
        """
        Permanently delete torrents. Removes files.

        :param infohash_list: Single or list() of infohashes.
        """
        return self._delete(infohash_list, True)

    def delete_all_permanently(self):
        """
        Permanently delete torrents.
        """
        return self._delete("all", True)

    def _delete(self, infohash_list, delete_files=False):
        """
        Delete torrents.

        :param infohash_list: Single or list() of infohashes.
        :param delete_files: Whether to delete files along with torrent.
        """
        data = self._process_infohash_list(infohash_list)
        data["deleteFiles"] = json.dumps(delete_files)
        return self._post("torrents/delete", data=data)

    def recheck(self, infohash_list):
        """
        Recheck torrents.

        :param infohash_list: Single or list() of infohashes.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/recheck", data=data)

    def recheck_all(self):
        """
        Recheck all torrents.
        """
        return self._post("torrents/recheck", data={"hashes": "all"})

    def reannounce(self, infohash_list):
        """
        Recheck all torrents.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        """

        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/reannounce", data=data)

    def increase_priority(self, infohash_list):
        """
        Increase priority of torrents.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/increasePrio", data=data)

    def decrease_priority(self, infohash_list):
        """
        Decrease priority of torrents.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/decreasePrio", data=data)

    def set_max_priority(self, infohash_list):
        """
        Set torrents to maximum priority level.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/topPrio", data=data)

    def set_min_priority(self, infohash_list):
        """
        Set torrents to minimum priority level.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/bottomPrio", data=data)

    def set_file_priority(self, infohash, file_id, priority):
        """
        Set file of a torrent to a supplied priority level.

        :param infohash: INFO HASH of torrent.
        :param file_id: ID of the file to set priority.
        :param priority: Priority level of the file.

        :note Priorities Don't download, Normal, High, Maximum
        in 3.2.0-4.1+ are 0, 1, 6, 7 and in 3.1.x are 0, 1, 2, 7
        """
        if priority not in [0, 1, 2, 4, 6, 7]:
            raise ValueError("Invalid priority, refer WEB-UI docs for info.")
        elif not isinstance(file_id, int):
            raise TypeError("File ID must be an int")

        data = {"hash": infohash.lower(), "id": file_id, "priority": priority}

        return self._post("torrents/filePrio", data=data)

    def set_automatic_torrent_management(self, infohash_list, enable="false"):
        """
        Set the category on multiple torrents.

        :param infohash_list: Single or list() of infohashes.
        :param enable: is a boolean, affects the torrents listed in infohash_list, default is 'false'
        """
        data = self._process_infohash_list(infohash_list)
        data["enable"] = enable
        return self._post("torrents/setAutoManagement", data=data)

    # Get-set global download and upload speed limits.

    def get_global_download_limit(self):
        """
        Get global download speed limit.
        """
        return self._get("transfer/downloadLimit")

    def set_global_download_limit(self, limit):
        """
        Set global download speed limit.

        :param limit: Speed limit in bytes.
        """
        return self._post("transfer/setDownloadLimit", data={"limit": limit})

    global_download_limit = property(get_global_download_limit, set_global_download_limit)

    def get_global_upload_limit(self):
        """
        Get global upload speed limit.
        """
        return self._get("transfer/uploadLimit")

    def set_global_upload_limit(self, limit):
        """
        Set global upload speed limit.

        :param limit: Speed limit in bytes.
        """
        return self._post("transfer/setUploadLimit", data={"limit": limit})

    global_upload_limit = property(get_global_upload_limit, set_global_upload_limit)

    # Get-set download and upload speed limits of the torrents.
    def get_torrent_download_limit(self, infohash_list):
        """
        Get download speed limit of the supplied torrents.

        :param infohash_list: Single or list() of infohashes.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/downloadLimit", data=data)

    def set_torrent_download_limit(self, infohash_list, limit):
        """
        Set download speed limit of the supplied torrents.

        :param infohash_list: Single or list() of infohashes.
        :param limit: Speed limit in bytes.
        """
        data = self._process_infohash_list(infohash_list)
        data.update({"limit": limit})
        return self._post("torrents/setDownloadLimit", data=data)

    def get_torrent_upload_limit(self, infohash_list):
        """
        Get upoload speed limit of the supplied torrents.

        :param infohash_list: Single or list() of infohashes.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/uploadLimit", data=data)

    def set_torrent_upload_limit(self, infohash_list, limit):
        """
        Set upload speed limit of the supplied torrents.

        :param infohash_list: Single or list() of infohashes.
        :param limit: Speed limit in bytes.
        """
        data = self._process_infohash_list(infohash_list)
        data.update({"limit": limit})
        return self._post("torrents/setUploadLimit", data=data)

    # setting preferences
    def set_preferences(self, **kwargs):
        """
        Set preferences of qBittorrent.
        Read all possible preferences @ https://git.io/fx2Y9

        :param kwargs: set preferences in kwargs form.
        """
        json_data = "json={}".format(json.dumps(kwargs))
        headers = {"content-type": "application/x-www-form-urlencoded"}
        return self._post("app/setPreferences", data=json_data, headers=headers)

    def get_alternative_speed_status(self):
        """
        Get Alternative speed limits. (1/0)
        """

        return self._get("transfer/speedLimitsMode")

    alternative_speed_status = property(get_alternative_speed_status)

    def toggle_alternative_speed(self):
        """
        Toggle alternative speed limits.
        """
        return self._post("transfer/toggleSpeedLimitsMode", data={})

    def toggle_sequential_download(self, infohash_list):
        """
        Toggle sequential download in supplied torrents.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/toggleSequentialDownload", data=data)

    def toggle_first_last_piece_priority(self, infohash_list):
        """
        Toggle first/last piece priority of supplied torrents.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        """
        data = self._process_infohash_list(infohash_list)
        return self._post("torrents/toggleFirstLastPiecePrio", data=data)

    def force_start(self, infohash_list, value):
        """
        Force start selected torrents.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        :param value: Force start value (bool)
        """
        data = self._process_infohash_list(infohash_list)
        data.update({"value": json.dumps(value)})
        return self._post("torrents/setForceStart", data=data)

    def set_super_seeding(self, infohash_list, value):
        """
        Set super seeding for selected torrents.

        :param infohash_list: Single or list() of infohashes; pass 'all' for all torrents.
        :param value: Force start value (bool)
        """
        data = self._process_infohash_list(infohash_list)
        data.update({"value": json.dumps(value)})
        return self._post("torrents/setSuperSeeding", data=data)

    def search(self, name, plugin="all", limit=500, offset=0):
        """
        Search for a torrent with the builtin search engine.
        :param name: name of torrent searched -> string.
        :param plugin: plugin used (default all, enabled for all the active ones) -> string.
        :param limit: result limit to return (default 500) -> int.
        :param offset: offset (default 0) -> int.
        """

        id = self._post(
            'search/start', {'pattern': name, 'category': 'all', 'plugins': plugin})

        # Wait while the search is running
        while self._post('search/results',
                         {'id': id['id'],
                          'limit': str(limit),
                          'offset': str(offset)})['status'] == "Running":
            sleep(0.5)

        # When finished return the results
        return self._post('search/results', {'id': id['id'], 'limit': str(limit), 'offset': str(offset)})

    def list_search_plugins(self):
        return self._get('search/plugins')

    def add_search_plugin(self, url):
        """
        Add search plugin.
        :param url: url of the raw file (see https://github.com/qbittorrent/search-plugins/wiki/Unofficial-search-plugins for precisions)
        """
        return self._post('search/installPlugin', {'sources': url})

    def disable_search_plugin(self, name):
        """
        Disable a specific search plugin.
        :param name: plugin name.
        """

        return self._post('search/enablePlugin', {'names': name, 'enable': 'false'})

    def enable_search_plugin(self, name):
        """
        Enable a specific search plugin.
        """

        return self._post('search/enablePlugin', {'names': name, 'enable': 'true'})

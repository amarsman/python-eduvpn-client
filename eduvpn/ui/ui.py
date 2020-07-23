# eduvpngui - The GNU/Linux eduVPN GUI client
#
# Copyright: 2017-2020, The Commons Conservancy eduVPN Programme
# SPDX-License-Identifier: GPL-3.0+

import os
import re
import webbrowser
from logging import getLogger
from pathlib import Path
from typing import Optional

logger = getLogger(__name__)

try:
    import gi

    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GObject, GLib, GdkPixbuf
except (ImportError, ValueError) as e:
    logger.warning("GTK not available")

from requests_oauthlib import OAuth2Session

from eduvpn.utils import get_prefix, thread_helper
from eduvpn.storage import get_uuid
from eduvpn.i18n import extract_translation, retrieve_country_name
from eduvpn.nm import get_client, save_connection, nm_available, activate_connection, deactivate_connection
from eduvpn.oauth2 import get_oauth
from eduvpn.remote import get_info, create_keypair, get_config, list_profiles
from eduvpn.settings import CLIENT_ID, FLAG_PREFIX, IMAGE_PREFIX, HELP_URL
from eduvpn.storage import set_token, get_token, set_api_url, set_auth_url, set_profile, write_config
from eduvpn.ui.backend import BackendData, ConnectionStatus

builder_files = ['mainwindow.ui']


class EduVpnGui:

    def __init__(self, lets_connect: bool) -> None:
        self.lets_connect = lets_connect

        self.prefix = get_prefix()
        self.builder = Gtk.Builder()

        self.client = get_client()

        for b in builder_files:
            p = os.path.join(self.prefix, 'share/eduvpn/builder', b)
            if not os.access(p, os.R_OK):
                logger.error(u"Can't find {}! That is quite an important file.".format(p))
                raise Exception
            self.builder.add_from_file(p)

        handlers = {
            "delete_window": Gtk.main_quit,
            "on_settings_button_released": self.on_settings_button_released,
            "on_help_button_released": self.on_help_button_released,
            "on_back_button_released": self.on_back_button_released,
            "on_search_changed": self.on_search_changed,
            "on_add_other_server_button_clicked": self.on_add_other_server_button_clicked,
            "on_cancel_browser_button_clicked": self.on_cancel_browser_button_clicked,
            "on_connection_switch_state_set": self.on_connection_switch_state_set
        }

        self.builder.connect_signals(handlers)
        self.window = self.builder.get_object('applicationWindow')

        self.back_button = self.builder.get_object('backButton')

        self.find_your_institute_page = self.builder.get_object('findYourInstitutePage')
        self.institute_tree_view = self.builder.get_object('instituteTreeView')
        self.secure_internet_tree_view = self.builder.get_object('secureInternetTreeView')
        self.other_servers_tree_view = self.builder.get_object('otherServersTreeView')
        self.find_your_institute_spacer = self.builder.get_object('findYourInstituteSpacer')
        self.find_your_institute_image = self.builder.get_object('findYourInstituteImage')
        self.add_other_server_top_row = self.builder.get_object('addOtherServerTopRow')
        self.institute_access_header = self.builder.get_object('instituteAccessHeader')
        self.secure_internet_header = self.builder.get_object('secureInternetHeader')
        self.other_servers_header = self.builder.get_object('otherServersHeader')
        self.find_your_institute_search = self.builder.get_object('findYourInstituteSearch')
        self.add_other_server_button = self.builder.get_object('addOtherServerButton')

        self.choose_profile_page = self.builder.get_object('chooseProfilePage')
        self.profile_tree_view = self.builder.get_object('profileTreeView')

        self.choose_location_page = self.builder.get_object('chooseLocationPage')
        self.location_tree_view = self.builder.get_object('locationTreeView')

        self.open_browser_page = self.builder.get_object('openBrowserPage')

        self.connection_page = self.builder.get_object('connectionPage')
        self.server_label = self.builder.get_object('serverLabel')
        self.server_image = self.builder.get_object('serverImage')
        self.support_label = self.builder.get_object('supportLabel')
        self.connection_status_image = self.builder.get_object('connectionStatusImage')
        self.connection_status_label = self.builder.get_object('connectionStatusLabel')
        self.connection_sub_status = self.builder.get_object('connectionSubStatus')
        self.profiles_sub_page = self.builder.get_object('profilesSubPage')
        self.current_connection_sub_page = self.builder.get_object('currentConnectionSubPage')
        self.connection_sub_page = self.builder.get_object('connectionSubPage')
        self.connection_info_top_row = self.builder.get_object('connectionInfoTopRow')
        self.connection_info_grid = self.builder.get_object('connectionInfoGrid')
        self.duration_value_label = self.builder.get_object('durationValueLabel')
        self.downloaded_value_label = self.builder.get_object('downloadedValueLabel')
        self.uploaded_value_label = self.builder.get_object('uploadedValueLabel')
        self.ipv4_value_label = self.builder.get_object('ipv4ValueLabel')
        self.ipv6_value_label = self.builder.get_object('ipv6ValueLabel')
        self.connection_info_bottom_row = self.builder.get_object('connectionInfoBottomRow')
        self.connection_switch = self.builder.get_object('connectionSwitch')
        # self.connection_switch.connect("notify::active", self.on_connection_switch_activated)

        self.settings_page = self.builder.get_object('settingsPage')

        self.data = BackendData()

        self.institute_list_model = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_INT)
        self.secure_internet_list_model = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_INT)
        self.other_servers_list_model = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_INT)
        self.profiles_list_model = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_INT)
        self.locations_list_model = Gtk.ListStore(GObject.TYPE_STRING, GdkPixbuf.Pixbuf, GObject.TYPE_INT)

        self.init_search_list()
        self.back_button.hide()
        self.add_other_server_top_row.hide()

    def run(self) -> None:
        self.window.show()
        self.show_find_your_institute()

    def on_settings_button_released(self, widget, event) -> None:
        logger.debug("on_settings_button_released")
        self.show_settings()

    def on_help_button_released(self, widget, event) -> None:
        logger.debug("on_help_button_released")
        webbrowser.open(HELP_URL)

    def on_back_button_released(self, widget, event) -> None:
        logger.debug("on_back_button_released")
        self.show_find_your_institute()

    def on_add_other_server_button_clicked(self, button) -> None:
        logger.debug("on_add_other_server_button_clicked")
        self.show_add_other_server()

    def on_other_server_selection_changed(self, selection) -> None:
        logger.debug("on_other_server_selection_changed")
        logger.debug("# selected rows:" + str(selection.count_selected_rows()))
        (model, tree_iter) = selection.get_selected()
        if tree_iter is not None:
            self.data.server_name = name = model[tree_iter][0]
            if name.count('.') > 1:
                if not name.lower().startswith('https://'):
                    name = 'https://' + name
                if not name.lower().endswith('/'):
                    name = name + '/'
                logger.debug("on_other_server_selection_changed: {}".format(name))
                select = self.institute_tree_view.get_selection()
                select.disconnect_by_func(self.on_institute_selection_changed)
                select = self.secure_internet_tree_view.get_selection()
                select.disconnect_by_func(self.on_secure_internet_selection_changed)
                select = self.other_servers_tree_view.get_selection()
                select.disconnect_by_func(self.on_other_server_selection_changed)
                self.setup_connection(name)
        selection.unselect_all()

    def on_cancel_browser_button_clicked(self, _) -> None:
        self.show_find_your_institute()

    def on_search_changed(self, _=None) -> None:
        logger.debug("on_search_changed: {}".format(self.find_your_institute_search.get_text()))
        self.update_search_lists(self.find_your_institute_search.get_text())

    def on_institute_selection_changed(self, selection) -> None:
        logger.debug("on_institute_selection_changed")
        logger.debug("# selected rows:" + str(selection.count_selected_rows()))
        (model, tree_iter) = selection.get_selected()
        if tree_iter is not None:
            self.data.server_name = model[tree_iter][0]
            i = model[tree_iter][1]
            select = self.institute_tree_view.get_selection()
            select.disconnect_by_func(self.on_institute_selection_changed)
            select = self.secure_internet_tree_view.get_selection()
            select.disconnect_by_func(self.on_secure_internet_selection_changed)
            select = self.other_servers_tree_view.get_selection()
            select.disconnect_by_func(self.on_other_server_selection_changed)
            base_url = str(self.data.institute_access[i]['base_url'])
            if 'support_contact' in self.data.institute_access[i]:
                self.data.support_contact = self.data.institute_access[i]['support_contact']
            logger.debug("on_institute_selection_changed: {} {}".format(self.data.server_name, base_url))
            self.setup_connection(base_url, None, False)
        selection.unselect_all()

    def on_secure_internet_selection_changed(self, selection) -> None:
        logger.debug("on_secure_internet_selection_changed")
        logger.debug("# selected rows:" + str(selection.count_selected_rows()))
        (model, tree_iter) = selection.get_selected()
        if tree_iter is not None:
            self.data.server_name = model[tree_iter][0]
            i = model[tree_iter][1]
            select = self.institute_tree_view.get_selection()
            select.disconnect_by_func(self.on_institute_selection_changed)
            select = self.secure_internet_tree_view.get_selection()
            select.disconnect_by_func(self.on_secure_internet_selection_changed)
            select = self.other_servers_tree_view.get_selection()
            select.disconnect_by_func(self.on_other_server_selection_changed)
            self.data.secure_internet_home = self.data.orgs[i]['secure_internet_home']
            logger.debug("on_secure_internet_selection_changed: {} {}".format(self.data.server_name, self.data.secure_internet_home))
            self.setup_connection(self.data.secure_internet_home, self.data.secure_internet, True)
        selection.unselect_all()

    def on_connection_switch_state_set(self, switch, state) -> None:
        if state:
            self.activate_connection()
        else:
            self.deactivate_connection()

    def activate_connection(self) -> None:
        logger.debug("Activating connection")
        uuid = get_uuid()
        if uuid:
            GLib.idle_add(lambda: activate_connection(self.client, uuid))
            GLib.idle_add(lambda: self.connection_activated())
        else:
            raise Exception("No UUID configured, can't activate connection")

    def deactivate_connection(self) -> None:
        logger.debug("Deactivating connection")
        uuid = get_uuid()
        if uuid:
            GLib.idle_add(lambda: deactivate_connection(self.client, uuid))
            GLib.idle_add(lambda: self.connection_deactivated())
        else:
            raise Exception("No UUID configured, can't deactivate connection")

    def connection_activated(self) -> None:
        self.update_connection(ConnectionStatus.CONNECTED)
        logger.debug("connection_activated")

    def connection_deactivated(self) -> None:
        self.update_connection(ConnectionStatus.NOT_CONNECTED)
        logger.debug("connection_deactivated")

    def init_search_list(self) -> None:
        text_cell = Gtk.CellRendererText()
        text_cell.set_property("size-points", 14)
        col = Gtk.TreeViewColumn(None, text_cell, text=0)
        self.institute_tree_view.append_column(col)
        self.institute_tree_view.set_model(self.institute_list_model)
        col = Gtk.TreeViewColumn(None, text_cell, text=0)
        self.secure_internet_tree_view.append_column(col)
        self.secure_internet_tree_view.set_model(self.secure_internet_list_model)
        col = Gtk.TreeViewColumn(None, text_cell, text=0)
        self.other_servers_tree_view.append_column(col)
        self.other_servers_tree_view.set_model(self.other_servers_list_model)
        col = Gtk.TreeViewColumn(None, text_cell, text=0)
        self.profile_tree_view.append_column(col)
        self.profile_tree_view.set_model(self.profiles_list_model)
        renderer_pixbuf = Gtk.CellRendererPixbuf()
        column_pixbuf = Gtk.TreeViewColumn("Image", renderer_pixbuf, pixbuf=1)
        self.location_tree_view.append_column(column_pixbuf)
        col = Gtk.TreeViewColumn(None, text_cell, text=0)
        self.location_tree_view.append_column(col)
        self.location_tree_view.set_model(self.locations_list_model)
        # self.update_search_lists()

    def update_search_lists(self, search_string="", disconnect=True) -> None:
        logger.debug("update_search_lists: {}".format(search_string))

        selection = self.institute_tree_view.get_selection()
        if disconnect:
            select = self.institute_tree_view.get_selection()
            select.disconnect_by_func(self.on_institute_selection_changed)
            select = self.secure_internet_tree_view.get_selection()
            select.disconnect_by_func(self.on_secure_internet_selection_changed)
            select = self.other_servers_tree_view.get_selection()
            select.disconnect_by_func(self.on_other_server_selection_changed)

        self.institute_list_model.clear()
        self.secure_internet_list_model.clear()
        self.other_servers_list_model.clear()
        for i, row in enumerate(self.data.institute_access):
            display_name = extract_translation(row['display_name'])
            if re.search(search_string, display_name, re.IGNORECASE):
                self.institute_list_model.append([display_name, i])
        for i, row in enumerate(self.data.orgs):
            display_name = extract_translation(row['display_name'])
            if re.search(search_string, display_name, re.IGNORECASE):
                self.secure_internet_list_model.append([display_name, i])
        self.show_search_lists()
        select = self.institute_tree_view.get_selection()
        select.connect("changed", self.on_institute_selection_changed)
        select = self.secure_internet_tree_view.get_selection()
        select.connect("changed", self.on_secure_internet_selection_changed)
        select = self.other_servers_tree_view.get_selection()
        select.connect("changed", self.on_other_server_selection_changed)

    def show_find_your_institute(self) -> None:
        logger.debug("show_find_your_institute")
        self.data.profiles = []
        self.data.locations = []
        self.data.secure_internet_home = None
        self.data.oauth = None
        self.data.api_url = None
        self.data.auth_url = None
        self.data.token_endpoint = None
        self.data.connection_status = ConnectionStatus.INITIALIZING
        self.data.server_name = None
        self.data.server_image = None
        self.data.support_contact = []

        self.find_your_institute_page.show()

        self.find_your_institute_search.disconnect_by_func(self.on_search_changed)
        self.find_your_institute_search.set_text("")

        self.settings_page.hide()
        self.choose_profile_page.hide()
        self.choose_location_page.hide()
        self.open_browser_page.hide()
        self.connection_page.hide()
        self.back_button.hide()
        self.add_other_server_top_row.hide()
        self.find_your_institute_search.connect("search-changed", self.on_search_changed)
        self.update_search_lists(disconnect=False)

    def show_add_other_server(self) -> None:
        logger.debug("show_add_other_server")
        self.find_your_institute_page.hide()
        self.settings_page.hide()
        self.choose_profile_page.hide()
        self.choose_location_page.hide()
        self.open_browser_page.hide()
        self.connection_page.hide()
        self.back_button.show()
        self.add_other_server_top_row.hide()

    def show_settings(self) -> None:
        logger.debug("show_settings")
        self.find_your_institute_page.hide()
        self.settings_page.show()
        self.choose_profile_page.hide()
        self.choose_location_page.hide()
        self.open_browser_page.hide()
        self.connection_page.hide()
        self.back_button.show()
        self.add_other_server_top_row.hide()

    def show_choose_profile(self) -> None:
        logger.debug("show_choose_profile")
        if len(self.data.profiles) > 1:
            self.find_your_institute_page.hide()
            self.settings_page.hide()
            self.choose_profile_page.show()
            self.choose_location_page.hide()
            self.open_browser_page.hide()
            self.connection_page.hide()
            self.back_button.show()
            self.add_other_server_top_row.hide()
            select = self.profile_tree_view.get_selection()
            select.connect("changed", self.on_profile_selection_changed)
        else:
            logger.debug("ERROR: should only be called when there are profiles to choose from")
            self.show_settings()

    def show_choose_location(self) -> None:
        logger.debug("show_choose_location")
        if len(self.data.locations) > 1:
            self.find_your_institute_page.hide()
            self.settings_page.hide()
            self.choose_profile_page.hide()
            self.choose_location_page.show()
            self.open_browser_page.hide()
            self.connection_page.hide()
            self.back_button.show()
            self.add_other_server_top_row.hide()
            select = self.location_tree_view.get_selection()
            select.connect("changed", self.on_location_selection_changed)
        else:
            logger.debug("ERROR: should only be called when there are profiles to choose from")
            self.show_settings()

    def show_open_browser(self) -> None:
        logger.debug("show_open_browser")
        self.find_your_institute_page.hide()
        self.settings_page.hide()
        self.choose_profile_page.hide()
        self.choose_location_page.hide()
        self.open_browser_page.show()
        self.connection_page.hide()
        self.back_button.hide()
        self.add_other_server_top_row.hide()

    def show_connection(self, connection_status) -> None:
        logger.debug("show_connection")
        self.find_your_institute_page.hide()
        self.settings_page.hide()
        self.choose_profile_page.hide()
        self.choose_location_page.hide()
        self.open_browser_page.hide()
        self.connection_page.show()
        self.back_button.show()
        self.add_other_server_top_row.hide()
        self.connection_info_top_row.hide()
        self.profiles_sub_page.hide()
        self.connection_sub_page.hide()
        self.connection_info_grid.hide()
        self.connection_info_bottom_row.hide()
        self.server_image.hide()
        self.server_label.set_text(self.data.server_name)
        logger.debug(self.data.server_image)
        if self.data.server_image is not None:
            self.server_image.set_from_file(self.data.server_image)
            self.server_image.show()
        else:
            self.server_image.hide()

        support = ""
        if len(self.data.support_contact) > 0:
            support = "Support: " + self.data.support_contact[0]
        self.support_label.set_text(support)
        self.update_connection(connection_status)

    def update_connection(self, status) -> None:
        self.data.connection_status = status

        if self.data.connection_status is ConnectionStatus.INITIALIZING:
            self.connection_status_label.set_text("Initializing")
            self.connection_status_image.set_from_file(IMAGE_PREFIX + "desktop-default.png")
            self.current_connection_sub_page.hide()
        elif self.data.connection_status is ConnectionStatus.NOT_CONNECTED:
            self.connection_status_label.set_text("Not connected")
            self.connection_status_image.set_from_file(IMAGE_PREFIX + "desktop-default.png")
            self.current_connection_sub_page.show()
        elif self.data.connection_status is ConnectionStatus.CONNECTING:
            self.connection_status_label.set_text("Connecting")
            self.connection_status_image.set_from_file(IMAGE_PREFIX + "desktop-connecting.png")
            self.current_connection_sub_page.show()
        elif self.data.connection_status is ConnectionStatus.CONNECTED:
            self.connection_status_label.set_text("Connected")
            self.connection_status_image.set_from_file(IMAGE_PREFIX + "desktop-connected.png")
            self.current_connection_sub_page.show()
        elif self.data.connection_status is ConnectionStatus.CONNECTION_ERROR:
            self.connection_status_label.set_text("Connection error")
            self.connection_status_image.set_from_file(IMAGE_PREFIX + "desktop-not-connected.png")
            self.current_connection_sub_page.show()

    def on_profile_selection_changed(self, selection) -> None:
        logger.debug("on_profile_selection_changed")
        logger.debug("# selected rows:" + str(selection.count_selected_rows()))
        (model, tree_iter) = selection.get_selected()
        if tree_iter is not None:
            display_name = model[tree_iter][0]
            i = model[tree_iter][1]
            selection.disconnect_by_func(self.on_profile_selection_changed)
            profile_id = str(self.data.profiles[i]['profile_id'])
            logger.debug("on_profile_selection_changed: {} {}".format(display_name, profile_id))
            self.finalize_configuration(profile_id)
        selection.unselect_all()

    def show_search_lists(self) -> None:
        name = self.find_your_institute_search.get_text()
        search_term = len(name) > 0
        dot_count = name.count('.')
        logger.debug("show_search_lists: name:{} len:{}".format(name, len(name)))

        if dot_count > 1:
            self.other_servers_list_model.clear()
            self.other_servers_list_model.append([name, 0])

        if search_term:
            self.find_your_institute_image.hide()
            self.find_your_institute_spacer.hide()
            self.add_other_server_top_row.hide()
        else:
            self.find_your_institute_image.show()
            self.find_your_institute_spacer.show()
            self.add_other_server_top_row.hide()

        if len(self.institute_list_model) > 0 and search_term:
            self.institute_access_header.show()
            self.institute_tree_view.show()
        else:
            self.institute_access_header.hide()
            self.institute_tree_view.hide()
        if len(self.secure_internet_list_model) > 0 and search_term:
            self.secure_internet_header.show()
            self.secure_internet_tree_view.show()
        else:
            self.secure_internet_header.hide()
            self.secure_internet_tree_view.hide()
        if len(self.other_servers_list_model) > 0 and search_term:
            self.other_servers_header.show()
            self.other_servers_tree_view.show()
        else:
            self.other_servers_header.hide()
            self.other_servers_tree_view.hide()

    def on_location_selection_changed(self, selection) -> None:
        logger.debug("on_location_selection_changed")
        logger.debug("# selected rows:" + str(selection.count_selected_rows()))
        (model, tree_iter) = selection.get_selected()
        if tree_iter is not None:
            self.data.server_name = model[tree_iter][0]
            display_name = model[tree_iter][0]
            i = model[tree_iter][2]
            selection.disconnect_by_func(self.on_location_selection_changed)
            logger.debug(self.data.locations[i])
            base_url = str(self.data.locations[i]['base_url'])
            country_code = self.data.locations[i]['country_code']
            self.data.server_image = FLAG_PREFIX + country_code + "@1,5x.png"
            if 'support_contact' in self.data.locations[i]:
                self.data.support_contact = self.data.locations[i]['support_contact']
            logger.debug("on_location_selection_changed: {} {}".format(display_name, base_url))
            self.show_connection(ConnectionStatus.INITIALIZING)
            thread_helper(lambda: handle_location_thread(base_url, self))
        selection.unselect_all()

    def setup_connection(self, auth_url, secure_internet: Optional[list] = None, interactive: bool = False) -> None:

        self.data.auth_url = auth_url
        self.data.locations = secure_internet
        logger.debug(f"starting procedure with auth_url {self.data.auth_url}")
        exists = get_token(self.data.auth_url)

        if exists:
            thread_helper(lambda: restoring_token_thread(exists, self))
        else:
            self.show_open_browser()
            thread_helper(lambda: fetch_token_thread(self))

    def token_available(self) -> None:
        if self.data.locations:
            thread_helper(lambda: handle_secure_internet_thread(self))
        else:
            self.handle_profiles()

    def handle_profiles(self) -> None:
        logger.debug(f"using {self.data.api_url} as api_url")
        thread_helper(lambda: handle_profiles_thread(self))

    def finalize_configuration(self, profile_id) -> None:
        logger.debug(f"finalize_configuration")
        self.show_connection(ConnectionStatus.INITIALIZING)
        thread_helper(lambda: finalize_configuration_thread(profile_id, self))

    def configuration_finalized(self, config, private_key, certificate) -> None:
        if nm_available():
            logger.info("nm available:")
            save_connection(self.client, config, private_key, certificate)
            GLib.idle_add(lambda: self.connection_saved())
        else:
            target = Path('eduVPN.ovpn').resolve()
            write_config(config, private_key, certificate, target)
            GLib.idle_add(lambda: self.connection_written())

    def connection_saved(self) -> None:
        logger.debug(f"connection_saved")
        self.show_connection(ConnectionStatus.NOT_CONNECTED)

    def connection_written(self) -> None:
        logger.debug(f"connection_written")
        self.show_connection(ConnectionStatus.NOT_CONNECTED)


def fetch_token_thread(gui) -> None:
    logger.debug("fetching token")
    gui.data.api_url, gui.data.token_endpoint, auth_endpoint = get_info(gui.data.auth_url)
    gui.data.oauth = get_oauth(gui.data.token_endpoint, auth_endpoint)
    set_token(gui.data.auth_url, gui.data.oauth.token, gui.data.token_endpoint, auth_endpoint)
    GLib.idle_add(lambda: gui.token_available())


def restoring_token_thread(exists, gui) -> None:
    logger.debug("token exists, restoring")
    token, gui.data.token_endpoint, authorization_endpoint = exists
    gui.data.oauth = OAuth2Session(client_id=CLIENT_ID, token=token, auto_refresh_url=gui.data.token_endpoint)
    gui.data.api_url, _, _ = get_info(gui.data.auth_url)
    GLib.idle_add(lambda: gui.token_available())


def handle_location_thread(base_url, gui) -> None:
    logger.debug("fetching location info")
    gui.data.api_url, _, _ = get_info(base_url)
    GLib.idle_add(lambda: gui.handle_profiles())


def handle_profiles_thread(gui) -> None:
    gui.data.oauth.refresh_token(token_url=gui.data.token_endpoint)
    gui.data.profiles = list_profiles(gui.data.oauth, gui.data.api_url)
    if len(gui.data.profiles) > 1:
        gui.profiles_list_model.clear()
        for i, profile in enumerate(gui.data.profiles):
            gui.profiles_list_model.append([profile['display_name'], i])
        GLib.idle_add(lambda: gui.show_choose_profile())
    else:
        profile_id = str(gui.data.profiles[0]['profile_id'])
        GLib.idle_add(lambda: gui.finalize_configuration(profile_id))


def handle_secure_internet_thread(gui) -> None:
    if len(gui.data.secure_internet) > 1:
        gui.locations_list_model.clear()
        for i, location in enumerate(gui.data.locations):
            flag_location = FLAG_PREFIX + location['country_code'] + "@1,5x.png"
            if os.path.exists(flag_location):
                flag_image = GdkPixbuf.Pixbuf.new_from_file(flag_location)
                gui.locations_list_model.append([retrieve_country_name(location['country_code']), flag_image, i])

        GLib.idle_add(lambda: gui.show_choose_location())
    else:
        base_url = str(gui.data.locations[0]['base_url'])
        GLib.idle_add(lambda: gui.finalize_configuration(base_url))


def finalize_configuration_thread(profile_id, gui: EduVpnGui) -> None:
    logger.debug("finalize_configuration_thread")
    config = get_config(gui.data.oauth, gui.data.api_url, profile_id)
    private_key, certificate = create_keypair(gui.data.oauth, gui.data.api_url)

    set_api_url(gui.data.api_url)
    set_auth_url(gui.data.auth_url)
    set_profile(profile_id)
    GLib.idle_add(lambda: gui.configuration_finalized(config, private_key, certificate))


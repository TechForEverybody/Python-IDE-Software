# -*- coding: utf-8 -*-
import itertools
import json
import os
import re
import subprocess
import sys
import tkinter as tk
import tkinter.font as tk_font
import urllib.error
import urllib.parse
from abc import ABC
from logging import exception, getLogger
from os import makedirs
from tkinter import messagebox, ttk
from tkinter.messagebox import showerror
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import thonny
from thonny import get_runner, get_workbench, running, tktextext, ui_utils
from thonny.common import (
    DistInfo,
    InlineCommand,
    normpath_with_actual_case,
    path_startswith,
    running_in_virtual_environment,
)
from thonny.languages import tr
from thonny.misc_utils import (
    construct_cmd_line,
    download_and_parse_json,
    download_bytes,
    jaro_similarity,
    levenshtein_distance,
)
from thonny.running import InlineCommandDialog, get_front_interpreter_for_subprocess
from thonny.ui_utils import (
    AutoScrollbar,
    CommonDialog,
    askopenfilename,
    ems_to_pixels,
    get_busy_cursor,
    get_hyperlink_cursor,
    lookup_style_option,
    open_path_in_system_file_manager,
    scrollbar_style,
)
from thonny.workdlg import SubprocessDialog

PIP_INSTALLER_URL = "https://bootstrap.pypa.io/get-pip.py"

logger = getLogger(__name__)

_EXTRA_MARKER_RE = re.compile(r"""^.*\bextra\s*==.+$""")


class PipDialog(CommonDialog, ABC):
    def __init__(self, master):
        self._state = "idle"  # possible values: "listing", "fetching", "idle"
        self._process = None
        self._closed = False
        self._active_distributions = {}
        self.current_package_data = None

        super().__init__(master)

        main_frame = ttk.Frame(self)
        main_frame.grid(sticky=tk.NSEW, ipadx=self.get_medium_padding())
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.title(self._get_title())

        self._create_widgets(main_frame)

        self.search_box.focus_set()

        self.bind("<Escape>", self._on_close, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._show_instructions()

        self._start_update_list()

    def get_search_button_text(self):
        return tr("Search on PyPI")

    def get_install_button_text(self):
        return tr("Install")

    def get_upgrade_button_text(self):
        return tr("Upgrade")

    def get_uninstall_button_text(self):
        return tr("Uninstall")

    def _create_widgets(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=self.get_medium_padding(),
            pady=(self.get_medium_padding(), 0),
        )
        header_frame.columnconfigure(0, weight=1)
        header_frame.rowconfigure(1, weight=1)

        default_font = tk_font.nametofont("TkDefaultFont")
        name_font = default_font.copy()
        name_font.configure(size=default_font["size"] * 2)
        self.search_box = ttk.Entry(header_frame)
        self.search_box.grid(row=1, column=0, sticky="nsew")
        self.search_box.bind("<Return>", self._on_search, False)
        self.search_box.bind("<KP_Enter>", self._on_search, False)

        # Selecting chars in the search box with mouse didn't make the box active on Linux without following line
        self.search_box.bind("<B1-Motion>", lambda _: self.search_box.focus_set())

        self.search_button = ttk.Button(
            header_frame,
            text=self.get_search_button_text(),
            command=self._on_search,
            width=len(self.get_search_button_text()) + 2,
        )
        self.search_button.grid(row=1, column=1, sticky="nse", padx=(self.get_small_padding(), 0))

        main_pw = tk.PanedWindow(
            parent,
            orient=tk.HORIZONTAL,
            background=lookup_style_option("TPanedWindow", "background"),
            sashwidth=self.get_large_padding(),
        )
        main_pw.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=self.get_medium_padding(),
            pady=(self.get_medium_padding(), self.get_medium_padding()),
        )
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        listframe = ttk.Frame(main_pw, relief="flat", borderwidth=1)
        listframe.rowconfigure(0, weight=1)
        listframe.columnconfigure(0, weight=1)

        self.listbox = ui_utils.ThemedListbox(
            listframe,
            activestyle="dotbox",
            width=20,
            height=23,
            selectborderwidth=0,
            relief="flat",
            # highlightthickness=4,
            # highlightbackground="red",
            # highlightcolor="green",
            borderwidth=0,
        )
        self.listbox.insert("end", " <" + tr("INSTALL") + ">")
        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select, True)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        list_scrollbar = AutoScrollbar(
            listframe, orient=tk.VERTICAL, style=scrollbar_style("Vertical")
        )
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        list_scrollbar["command"] = self.listbox.yview
        self.listbox["yscrollcommand"] = list_scrollbar.set

        info_frame = ttk.Frame(main_pw)
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(1, weight=1)

        main_pw.add(listframe)
        main_pw.add(info_frame)

        self.title_label = ttk.Label(info_frame, text="", font=name_font)
        self.title_label.grid(
            row=0, column=0, sticky="w", padx=0, pady=(0, self.get_large_padding())
        )

        info_text_frame = tktextext.TextFrame(
            info_frame,
            read_only=True,
            horizontal_scrollbar=False,
            background=lookup_style_option("TFrame", "background"),
            vertical_scrollbar_class=AutoScrollbar,
            vertical_scrollbar_style=scrollbar_style("Vertical"),
            horizontal_scrollbar_style=scrollbar_style("Horizontal"),
            padx=ems_to_pixels(0.1),
            pady=0,
            width=70,
            height=10,
        )
        info_text_frame.configure(borderwidth=0)
        info_text_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(0, 10))
        self.info_text = info_text_frame.text
        link_color = lookup_style_option("Url.TLabel", "foreground", "red")
        self.info_text.tag_configure("url", foreground=link_color, underline=True)
        self.info_text.tag_bind("url", "<ButtonRelease-1>", self._handle_url_click)
        self.info_text.tag_bind(
            "url", "<Enter>", lambda e: self.info_text.config(cursor=get_hyperlink_cursor())
        )
        self.info_text.tag_bind("url", "<Leave>", lambda e: self.info_text.config(cursor=""))
        self.info_text.tag_configure("install_reqs", foreground=link_color, underline=True)
        self.info_text.tag_bind(
            "install_reqs", "<ButtonRelease-1>", self._handle_install_requirements_click
        )
        self.info_text.tag_bind(
            "install_reqs",
            "<Enter>",
            lambda e: self.info_text.config(cursor=get_hyperlink_cursor()),
        )
        self.info_text.tag_bind(
            "install_reqs", "<Leave>", lambda e: self.info_text.config(cursor="")
        )
        self.info_text.tag_configure("install_file", foreground=link_color, underline=True)
        self.info_text.tag_bind(
            "install_file", "<ButtonRelease-1>", self._handle_install_file_click
        )
        self.info_text.tag_bind(
            "install_file",
            "<Enter>",
            lambda e: self.info_text.config(cursor=get_hyperlink_cursor()),
        )
        self.info_text.tag_bind(
            "install_file", "<Leave>", lambda e: self.info_text.config(cursor="")
        )

        self.info_text.configure(font=default_font, wrap="word")

        bold_font = default_font.copy()
        # need to explicitly copy size, because Tk 8.6 on certain Ubuntus use bigger font in copies
        bold_font.configure(weight="bold", size=default_font.cget("size"))
        self.info_text.tag_configure("caption", font=bold_font)
        self.info_text.tag_configure("bold", font=bold_font)
        self.info_text.tag_configure("right", justify="right")

        self.command_frame = ttk.Frame(info_frame)
        self.command_frame.grid(row=2, column=0, sticky="w")

        self.install_button = ttk.Button(
            self.command_frame,
            text=" " + self.get_upgrade_button_text() + " ",
            command=self._on_install_click,
            width=20,
        )

        self.install_button.grid(row=0, column=0, sticky="w", padx=0)

        self.uninstall_button = ttk.Button(
            self.command_frame,
            text=self.get_uninstall_button_text(),
            command=self._on_uninstall_click,
            width=20,
        )

        self.uninstall_button.grid(row=0, column=1, sticky="w", padx=(self.get_small_padding(), 0))

        self.advanced_button = ttk.Button(
            self.command_frame,
            text="...",
            width=3,
            command=lambda: self._perform_pip_action("advanced"),
        )

        self.advanced_button.grid(row=0, column=2, sticky="w", padx=(self.get_small_padding(), 0))

        self.close_button = ttk.Button(info_frame, text=tr("Close"), command=self._on_close)
        self.close_button.grid(row=2, column=3, sticky="e")

    def _set_state(self, state, force_normal_cursor=False):
        self._state = state
        action_buttons = [
            self.install_button,
            self.advanced_button,
            self.uninstall_button,
        ]

        other_widgets = [
            self.listbox,
            # self.search_box, # looks funny when disabled
            self.search_button,
        ]

        if state == "idle" and not self._is_read_only():
            for widget in action_buttons:
                widget["state"] = tk.NORMAL
        else:
            for widget in action_buttons:
                widget["state"] = tk.DISABLED

        if state == "idle":
            for widget in other_widgets:
                widget["state"] = tk.NORMAL
        else:
            self.config(cursor=get_busy_cursor())
            for widget in other_widgets:
                widget["state"] = tk.DISABLED

        if state == "idle" or force_normal_cursor:
            self.config(cursor="")
        else:
            self.config(cursor=get_busy_cursor())

    def _get_state(self):
        return self._state

    def _start_update_list(self, name_to_show=None):
        raise NotImplementedError()

    def _update_list(self, name_to_show):
        self.listbox.delete(1, "end")
        for name in sorted(self._active_distributions.keys()):
            self.listbox.insert("end", " " + name)

        if name_to_show is None or name_to_show not in self._active_distributions.keys():
            self._show_instructions()
        else:
            self._on_listbox_select_package(name_to_show)

    def _on_listbox_select(self, event):
        self.listbox.focus_set()
        selection = self.listbox.curselection()
        if len(selection) == 1:
            self.listbox.activate(selection[0])
            if selection[0] == 0:  # special first item
                self._show_instructions()
            else:
                self._on_listbox_select_package(self.listbox.get(selection[0]).strip())

    def _on_listbox_select_package(self, name):
        self._start_show_package_info(name)

    def _on_search(self, event=None):
        if self._get_state() != "idle":
            # Search box is not made inactive for busy-states
            return

        if self.search_box.get().strip() == "":
            return

        self._start_search(self.search_box.get().strip())

    def _on_install_click(self):
        self._perform_pip_action("install")

    def _on_uninstall_click(self):
        self._perform_pip_action("uninstall")

    def _clear(self):
        self.current_package_data = None
        self.title_label.grid_remove()
        self.command_frame.grid_remove()
        self._clear_info_text()

    def _clear_info_text(self):
        self.info_text.direct_delete("1.0", "end")

    def _append_info_text(self, text, tags=()):
        self.info_text.direct_insert("end", text, tags)

    def _show_instructions(self):
        self._clear()
        if self._is_read_only():
            self._show_read_only_instructions()
        else:
            self._show_instructions_about_installing_from_pypi()
            if self._installer_runs_locally():
                self._show_instructions_about_installing_from_requirements_file()
                self._show_instructions_about_installing_from_local_file()
            self._show_instructions_about_existing_packages()

            if self._get_target_directory():
                self._show_instructions_about_target()

            self._show_extra_instructions()

        self._select_list_item(0)

    def _show_extra_instructions(self):
        pass

    def _show_read_only_instructions(self):
        self._append_info_text(tr("Browse the packages") + "\n", ("caption",))
        self.info_text.direct_insert(
            "end",
            tr(
                "With current interpreter you can only browse the packages here.\n"
                + "Use 'Tools → Open system shell...' for installing, upgrading or uninstalling."
            )
            + "\n\n",
        )

        if self._get_target_directory():
            self._append_info_text(tr("Packages' directory") + "\n", ("caption",))
            self.info_text.direct_insert("end", self._get_target_directory(), ("target_directory"))

    def _show_instructions_about_installing_from_pypi(self):
        self._append_info_text(tr("Install from PyPI") + "\n", ("caption",))
        self.info_text.direct_insert(
            "end",
            tr(
                "If you don't know where to get the package from, "
                + "then most likely you'll want to search the Python Package Index. "
                + "Start by entering the name of the package in the search box above and pressing ENTER."
            )
            + "\n\n",
        )

    def _show_instructions_about_installing_from_requirements_file(self):
        self.info_text.direct_insert(
            "end", tr("Install from requirements file") + "\n", ("caption",)
        )
        self._append_info_text(tr("Click" + " "))
        self._append_info_text(tr("here"), ("install_reqs",))
        self.info_text.direct_insert(
            "end",
            " "
            + tr("to locate requirements.txt file and install the packages specified in it.")
            + "\n\n",
        )

    def _show_instructions_about_installing_from_local_file(self):
        self._append_info_text(tr("Install from local file") + "\n", ("caption",))
        self._append_info_text(tr("Click") + " ")
        self._append_info_text(tr("here"), ("install_file",))
        self.info_text.direct_insert(
            "end",
            " "
            + tr(
                "to locate and install the package file (usually with .whl, .tar.gz or .zip extension)."
            )
            + "\n\n",
        )

    def _show_instructions_about_existing_packages(self):
        self._append_info_text(tr("Upgrade or uninstall") + "\n", ("caption",))
        self.info_text.direct_insert(
            "end", tr("Start by selecting the package from the left.") + "\n\n"
        )

    def _show_instructions_about_target(self):
        self._append_info_text(tr("Target") + "\n", ("caption",))
        if self._use_user_install():
            self.info_text.direct_insert(
                "end",
                tr(
                    "This dialog lists all available packages,"
                    + " but allows upgrading and uninstalling only packages from"
                )
                + " ",
            )
            self._append_info_text(self._get_target_directory(), ("url"))
            self.info_text.direct_insert(
                "end",
                ". "
                + tr(
                    "New packages will be also installed into this directory."
                    + " Other locations must be managed by alternative means."
                ),
            )
        else:
            self._append_info_text(self._get_target_directory(), ("url"))

    def _get_package_metadata_url(self, name: str, version_str: Optional[str]) -> str:
        # Fetch info from PyPI
        if version_str is None:
            return "https://pypi.org/pypi/{}/json".format(urllib.parse.quote(name))
        else:
            return "https://pypi.org/pypi/{}/{}/json".format(
                urllib.parse.quote(name), urllib.parse.quote(version_str)
            )

    def _get_package_metadata_fallback_url(
        self, name: str, version_str: Optional[str]
    ) -> Optional[str]:
        return None

    def _download_package_info(self, name: str, version_str: Optional[str]) -> Dict:
        import json
        from urllib.request import urlopen

        """Running in a background thread"""
        # Fetch info from PyPI
        if version_str is None:
            url = "https://pypi.org/pypi/{}/json".format(urllib.parse.quote(name))
        else:
            url = "https://pypi.org/pypi/{}/{}/json".format(
                urllib.parse.quote(name), urllib.parse.quote(version_str)
            )

        logger.info("Downloading package info from %s", url)
        with urlopen(url) as fp:
            return json.load(fp)

    def _start_show_package_info(self, name):
        self.current_package_data = None
        # Fetch info from PyPI
        self._set_state("fetching")

        self._clear_info_text()
        self.title_label["text"] = ""
        self.title_label.grid()
        self.command_frame.grid()
        self.uninstall_button["text"] = self.get_uninstall_button_text()

        active_dist = self._get_active_dist(name)
        if active_dist is not None:
            self.title_label["text"] = active_dist.project_name
            self._append_info_text(tr("Installed version:") + " ", ("caption",))
            self._append_info_text(active_dist.version + "\n")
            self._append_info_text(tr("Installed to:") + " ", ("caption",))
            self._append_location_to_info_path(active_dist.location)
            self._append_info_text("\n\n")
            self._select_list_item(name)
        else:
            self._select_list_item(0)

        # update gui
        if self._is_read_only_package(name):
            self.install_button.grid_remove()
            self.uninstall_button.grid_remove()
            self.advanced_button.grid_remove()
        else:
            self.install_button.grid(row=0, column=0)
            self.advanced_button.grid(row=0, column=2)

            if active_dist is not None:
                # existing package in target directory
                self.install_button["text"] = self.get_upgrade_button_text()
                self.install_button["state"] = "disabled"
                self.uninstall_button.grid(row=0, column=1)
            else:
                # new package
                self.install_button["text"] = self.get_install_button_text()
                self.uninstall_button.grid_remove()

        # start download and polling
        from concurrent.futures.thread import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        download_future = executor.submit(self._download_package_info, name, None)

        def poll_fetch_complete():
            if download_future.done():
                try:
                    data = download_future.result()
                    if "info" in data and "name" not in data["info"]:
                        # this is the case of micropython.org/pi
                        data["info"]["name"] = name
                    self._show_package_info(name, data)
                except urllib.error.HTTPError as e:
                    self._show_package_info(
                        name, {"info": {"name": name}, "error": str(e), "releases": {}}, e.code
                    )
                except Exception as e:
                    self._show_package_info(
                        name, {"info": {"name": name}, "error": str(e), "releases": {}}, e
                    )
            else:
                get_workbench().after(200, poll_fetch_complete)

        poll_fetch_complete()

    def _append_location_to_info_path(self, path):
        self.info_text.direct_insert("end", path)

    def _show_package_info(self, name, data, error_code=None):
        self._set_state("idle")

        self.current_package_data = data

        def write(s, tag=None):
            if tag is None:
                tags = ()
            else:
                tags = (tag,)
            self._append_info_text(s, tags)

        def write_att(caption, value, value_tag=None):
            if value is None:
                return
            write(caption + ": ", "caption")
            write(value, value_tag)
            write("\n")

        if error_code is not None:
            if error_code == 404:
                write(tr("Could not find the package from PyPI."))
                if not self._get_active_version(name):
                    # new package
                    write("\n" + tr("Please check your spelling!"))

            else:
                write(
                    tr("Could not find the package info from PyPI.")
                    + " "
                    + tr("Error code:")
                    + " "
                    + str(error_code)
                )
                logger.exception("Coult not fetch package info for %r", name)

            return

        info = data["info"]
        # NB! Json from micropython.org index doesn't have all the same fields as PyPI!
        self.title_label["text"] = info["name"]  # search name could have been a bit different
        latest_stable_version = _get_latest_stable_version(data["releases"].keys())
        if latest_stable_version is not None:
            write_att(tr("Latest stable version"), latest_stable_version)
        else:
            write_att(tr("Latest version"), info["version"])
        if "summary" in info:
            write_att(tr("Summary"), info["summary"])
        if "author" in info:
            write_att(tr("Author"), info["author"])
        if "license" in info:
            write_att(tr("License"), info["license"])
        if "home_page" in info:
            write_att(tr("Homepage"), info["home_page"], "url")
        if info.get("bugtrack_url", None):
            write_att(tr("Bugtracker"), info["bugtrack_url"], "url")
        if info.get("docs_url", None):
            write_att(tr("Documentation"), info["docs_url"], "url")
        if info.get("package_url", None):
            write_att(tr("PyPI page"), info["package_url"], "url")
        if info.get("requires_dist", None):
            # Available only when release is created by a binary wheel
            # https://github.com/pypa/pypi-legacy/issues/622#issuecomment-305829257
            requires_dist = info["requires_dist"]
            assert isinstance(requires_dist, list)
            assert all(isinstance(item, str) for item in requires_dist)

            # See https://www.python.org/dev/peps/pep-0345/#environment-markers.
            # This will filter only the most obvious dependencies marked simply with
            # ``extras == *``.
            # The other, more complex markings, are accepted as they are also
            # more informative (*e.g.*, the desired platform).
            remaining_requires_dist = []  # type: List[str]

            for item in requires_dist:
                if ";" not in item:
                    remaining_requires_dist.append(item)
                    continue

                _, marker_text = item.split(";", 1)

                # Check if the environment marker matches ``extra == '*'.
                #
                # This is easier implemented with ``packaging.markers``, but we want to
                # avoid introducing a new dependency as Thonny is included in
                # distributions which might lack a package for it.
                #
                # Please see
                # https://packaging.pypa.io/en/latest/_modules/packaging/markers.html#Marker
                # for the parsing rules.

                # Match extra == quoted string
                is_extra = _EXTRA_MARKER_RE.match(marker_text) is not None

                if is_extra:
                    continue

                remaining_requires_dist.append(item)

            write_att(tr("Requires"), ", ".join(remaining_requires_dist))

        if self._get_active_version(name) != latest_stable_version or not self._get_active_version(
            name
        ):
            self.install_button["state"] = "normal"
        else:
            self.install_button["state"] = "disabled"

    def _is_read_only_package(self, name):
        dist = self._get_active_dist(name)
        if dist is None:
            return False
        else:
            return self._normalize_target_path(dist.location) != self._get_target_directory()

    def _normalize_name(self, name):
        return canonicalize_name(name)

    def _normalize_target_path(self, path: str) -> str:
        return path

    def _start_search(self, query, discard_selection=True):
        self.current_package_data = None
        # Fetch info from PyPI
        self._set_state("fetching")
        self._clear()
        self.title_label.grid()
        self.title_label["text"] = tr("Search results")
        self.info_text.direct_insert("1.0", tr("Searching") + " ...")
        if discard_selection:
            self._select_list_item(0)

        from concurrent.futures.thread import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        results_future = executor.submit(self._fetch_search_results, query)

        def poll_fetch_complete():
            if results_future.done():
                try:
                    results = results_future.result()
                except OSError as e:
                    self._show_search_results(query, str(e))
                else:
                    self._show_search_results(query, results)

            else:
                get_workbench().after(200, poll_fetch_complete)

        poll_fetch_complete()

    def _show_search_results(self, query, results: Union[Dict[str, List[Dict]], str]) -> None:
        self._set_state("idle")
        self._clear_info_text()

        if isinstance(results, str) or not results:
            if not results:
                self._append_info_text("No results.\n\n")
            else:
                self._append_info_text("Could not fetch search results:\n")
                self._append_info_text(results + "\n\n")

            self._append_info_text("Try opening the package directly:\n")
            self._append_info_text(query, ("url",))
            return

        for source, source_results in results.items():
            if len(results) > 1:
                self._append_info_text(source + "\n", tags=("caption",))

            for item in source_results:
                # self._append_info_text("•")
                tags = ("url",)
                if item["name"].lower() == query.lower():
                    tags = tags + ("bold",)

                self._append_info_text(item["name"], tags)
                if item.get("source"):
                    self._append_info_text(" @ " + item["source"])
                self._append_info_text("\n")
                self.info_text.direct_insert(
                    "end", (item.get("description") or "<No description>").strip() + "\n"
                )
                self._append_info_text("\n")

    def _select_list_item(self, name_or_index):
        if isinstance(name_or_index, int):
            index = name_or_index
        else:
            normalized_items = list(map(self._normalize_name, self.listbox.get(0, "end")))
            try:
                index = normalized_items.index(self._normalize_name(name_or_index))
            except Exception:
                exception(tr("Can't find package name from the list:") + " " + name_or_index)
                return

        old_state = self.listbox["state"]
        try:
            self.listbox["state"] = "normal"
            self.listbox.select_clear(0, "end")
            self.listbox.select_set(index)
            self.listbox.activate(index)
            self.listbox.see(index)
        finally:
            self.listbox["state"] = old_state

    def _perform_pip_action(self, action: str) -> None:
        if self._perform_pip_action_without_refresh(action):
            if action == "uninstall":
                self._show_instructions()  # Make the old package go away as fast as possible
            self._start_update_list(
                None if action == "uninstall" else self.current_package_data["info"]["name"]
            )

            if self._has_remote_target():
                get_workbench().event_generate("RemoteFilesChanged")

    def _perform_pip_action_without_refresh(self, action: str) -> bool:
        """Returns whether the action was at least started and some packages might have been
        modified.
        """
        assert self._get_state() == "idle"
        assert self.current_package_data is not None
        data = self.current_package_data
        name = self.current_package_data["info"]["name"]

        install_args = ["--progress-bar", "off"]
        if self._use_user_install():
            install_args.append("--user")

        if action == "install":
            command = "install"
            title = tr("Installing '%s'") % name
            if not self._confirm_install(self.current_package_data):
                return False

            args = install_args
            if self._get_active_version(name) is not None:
                title = tr("Upgrading '%s'") % name
                args.append("--upgrade")

            args.append(name)

        elif action == "uninstall":
            command = "uninstall"
            title = tr("Uninstalling '%s'") % name
            if name in ["pip", "setuptools"] and not messagebox.askyesno(
                tr("Really uninstall?"),
                tr(
                    "Package '{}' is required for installing and uninstalling other packages."
                ).format(name)
                + "\n\n"
                + tr("Are you sure you want to uninstall it?"),
                master=self,
            ):
                return False
            args = ["--yes", name]
        elif action == "advanced":
            command = "install"
            title = tr("Installing")
            details = _ask_installation_details(
                self,
                data,
                _get_latest_stable_version(list(data["releases"].keys())),
                self.does_support_update_deps_switch(),
            )
            if details is None:  # Cancel
                return False

            version, package_data, upgrade_deps = details
            if not self._confirm_install(package_data):
                return False

            args = install_args
            if upgrade_deps:
                args.append("--upgrade")

            args.append(name + "==" + version)
        else:
            raise RuntimeError("Unknown action")

        self._run_pip_with_dialog(command, args, title=title)
        return True

    def does_support_update_deps_switch(self):
        return True

    def _handle_install_file_click(self, event):
        if self._get_state() != "idle":
            return

        filename = askopenfilename(
            master=self,
            filetypes=[(tr("Package"), ".whl .zip .tar.gz"), (tr("all files"), ".*")],
            initialdir=get_workbench().get_local_cwd(),
            parent=self.winfo_toplevel(),
        )
        if filename:  # Note that missing filename may be "" or () depending on tkinter version
            self._install_file(filename, False)

    def _handle_install_requirements_click(self, event):
        if self._get_state() != "idle":
            return

        filename = askopenfilename(
            master=self,
            filetypes=[("requirements", ".txt"), (tr("all files"), ".*")],
            initialdir=get_workbench().get_local_cwd(),
            parent=self.winfo_toplevel(),
        )
        if filename:  # Note that missing filename may be "" or () depending on tkinter version
            self._install_file(filename, True)

    def _handle_target_directory_click(self, event):
        if self._get_target_directory():
            open_path_in_system_file_manager(self._get_target_directory())

    def _install_file(self, filename, is_requirements_file):
        args = self._get_install_file_command(filename, is_requirements_file)

        returncode, out, err = self._run_pip_with_dialog(
            command="install", args=args, title=tr("Installing '%s'") % os.path.basename(filename)
        )

        # Try to find out the name of the package we're installing
        name = None

        # output should include a line like this:
        # Installing collected packages: pytz, six, python-dateutil, numpy, pandas
        inst_lines = re.findall(
            "^Installing collected packages:.*?$", out, re.MULTILINE | re.IGNORECASE
        )  # @UndefinedVariable
        if len(inst_lines) == 1:
            # take last element
            elements = re.split("[,:]", inst_lines[0])
            name = elements[-1].strip()

        self._start_update_list(name)

    def _get_install_file_command(self, filename, is_requirements_file):
        args = []
        if self._use_user_install():
            args.append("--user")
        if is_requirements_file:
            args.append("-r")
        args.append(filename)

        return args

    def _handle_url_click(self, event):
        url = _extract_click_text(self.info_text, event, "url")
        if url is not None:
            if url.startswith("http:") or url.startswith("https:"):
                import webbrowser

                webbrowser.open(url)
            elif os.path.sep in url:
                os.makedirs(url, exist_ok=True)
                open_path_in_system_file_manager(url)
            else:
                self._start_show_package_info(url)

    def _on_close(self, event=None):
        self._closed = True
        self.destroy()

    def _get_active_version(self, name):
        dist = self._get_active_dist(name)
        if dist is None:
            return None
        else:
            return dist.version

    def _get_active_dist(self, name):
        normname = self._normalize_name(name)
        for key in self._active_distributions:
            if self._normalize_name(key) == normname:
                return self._active_distributions[key]

        return None

    def _run_pip_with_dialog(
        self, command: str, args: List[str], title: str
    ) -> Tuple[int, str, str]:
        raise NotImplementedError()

    def _get_interpreter_description(self):
        raise NotImplementedError()

    def _use_user_install(self):
        raise NotImplementedError()

    def _targets_virtual_environment(self):
        return False

    def _has_remote_target(self):
        raise NotImplementedError()

    def _installer_runs_locally(self):
        raise NotImplementedError()

    def _get_target_directory(self):
        raise NotImplementedError()

    def _get_title(self):
        return tr("Manage packages for %s") % self._get_interpreter_description()

    def _confirm_install(self, package_data):
        return True

    def _is_read_only(self):
        raise NotImplementedError()

    def _fetch_search_results(self, query: str) -> Dict[str, List[Dict[str, str]]]:
        """Will be executed in background thread"""
        return {
            "*": self._perform_pypi_search(
                query,
                source=None,
                data_url=get_workbench().get_data_url("pypi_summaries_cpython.json"),
                common_tokens=[],
            )
        }

    def _perform_pypi_search(
        self, query: str, source: Optional[str], data_url: str, common_tokens: List[str]
    ) -> List[Dict[str, str]]:
        logger.info("Performing PyPI search for %r", query)

        data = download_bytes(data_url)
        packages: List[Dict] = json.loads(data)

        canonical_query = canonicalize_name(query)
        query_parts = canonical_query.split("-")
        for package in packages:
            package["score"] = compute_dist_name_similarity(
                package["name"], query_parts, common_tokens
            )

        packages.sort(key=lambda p: p["score"], reverse=True)

        if not packages or packages[0]["score"] < 1.0:
            # test for exact match
            try:
                dist_data = download_dist_data_from_pypi(canonical_query, None)
                dist_info = dist_data["info"]
                print(dist_info)
                packages.insert(
                    0,
                    {"name": dist_info["name"], "summary": dist_info.get("summary"), "score": 1.0},
                )
            except Exception:
                logger.info("No luck with exact match %r", canonical_query)

        return [
            dict(
                name=p["name"],
                version="0",
                description=p.get("summary"),
                source=source,
                distance=levenshtein_distance(query, p["name"]),
            )
            for p in packages[:20]
            if p["score"] > 0.6
        ]


def canonicalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower().strip()


def _get_sublists_of_length(l: List[Any], n: int) -> List[List[Any]]:
    return [l[i : i + n] for i in range(len(l) - n + 1)]


def compute_dist_name_similarity(
    name: str, query_parts: List[str], common_tokens: List[str]
) -> float:
    name_parts = (name).split("-")

    for common_token in common_tokens:
        if common_token in name_parts and common_token not in query_parts:
            # don't penalize omitting this part
            name_parts.remove(common_token)

    common_count = min(len(query_parts), len(name_parts))
    name_perms = list(itertools.permutations(name_parts, common_count))
    query_perms = list(itertools.permutations(query_parts, common_count))

    if len(name_perms) * len(query_perms) > 36:
        # 36 corresponds to 3-part name and 3-part query.
        # More than that would be too much effort. Assume correct order and match sub-lists instead.
        name_perms = _get_sublists_of_length(name_parts, common_count)
        query_perms = _get_sublists_of_length(query_parts, common_count)

    best_score = 0
    for name_perm, query_perm in itertools.product(name_perms, query_perms):
        score = jaro_similarity("-".join(name_perm), "-".join(query_perm))
        best_score = max(score, best_score)

    parts_length_penalty = 1.0 - abs(len(query_parts) - len(name_parts)) * 0.05
    return best_score * parts_length_penalty


class BackendPipDialog(PipDialog):
    def __init__(self, master):
        self._backend_proxy = get_runner().get_backend_proxy()
        super().__init__(master)

        self._last_name_to_show = None

    def _has_remote_target(self):
        return get_runner().get_backend_proxy().supports_remote_files()

    def _start_update_list(self, name_to_show=None):
        assert self._get_state() in [None, "idle"]
        self._set_state("listing")

        get_workbench().bind("get_active_distributions_response", self._complete_update_list, True)
        self._last_name_to_show = name_to_show
        logger.debug("Sending get_active_distributions")
        get_runner().send_command(InlineCommand("get_active_distributions"))

    def _complete_update_list(self, msg):
        if self._closed:
            return

        get_workbench().unbind("get_active_distributions_response", self._complete_update_list)
        if "error" in msg:
            self._clear_info_text()
            self.info_text.direct_insert("1.0", msg["error"])
            self._set_state("idle", True)
            return

        self._active_distributions = msg.distributions
        self._set_state("idle", True)
        self._update_list(self._last_name_to_show)

    def _confirm_install(self, package_data):
        name = package_data["info"]["name"]

        if name.lower().startswith("thonny"):
            return messagebox.askyesno(
                tr("Confirmation"),
                tr(
                    "Looks like you are installing a Innovator-related package.\n"
                    + "If you meant to install a Innovator plugin, then you should\n"
                    + "choose 'Tools → Manage plugins...' instead\n"
                    + "\n"
                    + "Are you sure you want to install %s for the back-end?"
                )
                % name,
                master=self,
            )
        else:
            return True

    def _run_pip_with_dialog(
        self, command: str, args: List[str], title: str
    ) -> Tuple[int, str, str]:
        proxy = get_runner().get_backend_proxy()
        if command == "install":
            back_cmd = InlineCommand("install_distributions", args=args)
        elif command == "uninstall":
            back_cmd = InlineCommand("uninstall_distributions", args=args)
        else:
            raise AssertionError(f"Unexpected command {command}")

        dlg = InlineCommandDialog(
            self,
            back_cmd,
            title=command,
            instructions=title,
            autostart=True,
            output_prelude=f"{command} {construct_cmd_line(args)}\n",
        )
        ui_utils.show_dialog(dlg)

        return dlg.returncode, dlg.stdout, dlg.stderr


class PluginsPipDialog(PipDialog):
    def __init__(self, master):
        PipDialog.__init__(self, master)

        # make sure directory exists, so user can put her plug-ins there
        d = self._get_target_directory()
        makedirs(d, exist_ok=True)

    def _has_remote_target(self):
        return False

    def _installer_runs_locally(self):
        return True

    def _is_read_only(self):
        return False

    def _start_update_list(self, name_to_show=None):
        assert self._get_state() in [None, "idle"]
        import pkg_resources

        pkg_resources._initialize_master_working_set()

        self._active_distributions = {
            dist.key: DistInfo(
                project_name=dist.project_name,
                key=dist.key,
                location=dist.location,
                version=dist.version,
            )
            for dist in pkg_resources.working_set  # pylint: disable=not-an-iterable
        }

        self._update_list(name_to_show)

    def _conflicts_with_thonny_version(self, req_strings):
        import pkg_resources

        try:
            conflicts = []
            for req_string in req_strings:
                req = pkg_resources.Requirement.parse(req_string)
                if req.project_name == "thonny" and thonny.get_version() not in req:
                    conflicts.append(req_string)

            return conflicts
        except Exception:
            logger.exception("Problem computing conflicts")
            return None

    def _get_interpreter_description(self):
        return get_front_interpreter_for_subprocess(sys.executable)

    def _use_user_install(self):
        return not self._targets_virtual_environment()

    def _targets_virtual_environment(self):
        return running_in_virtual_environment()

    def _confirm_install(self, package_data):
        name = package_data["info"]["name"]
        reqs = package_data["info"].get("requires_dist", None)

        other_version_text = tr(
            "NB! There may be another version available "
            + "which is compatible with current Innovator version. "
            + "Click on '...' button to choose the version to install."
        )

        if name.lower().startswith("thonny-") and not reqs:
            showerror(
                tr("Innovator plugin without requirements"),
                (
                    "Looks like you are trying to install an outdated Thonny\n"
                    + "plug-in (it doesn't specify required Innovator version\n"
                    + "or hasn't uploaded a whl file before other files).\n\n"
                    + "If you still want it, then please install it from the command line."
                )
                + "\n\n"
                + other_version_text,
                master=self,
            )
            return False
        elif reqs:
            conflicts = self._conflicts_with_thonny_version(reqs)
            if conflicts:
                showerror(
                    tr("Unsuitable requirements"),
                    tr("This package requires different Innovator version:")
                    + "\n\n  "
                    + "\n  ".join(conflicts)
                    + "\n\n"
                    + tr("If you still want it, then please install it from the command line.")
                    + "\n\n"
                    + other_version_text,
                    master=self,
                )
                return False

        return True

    def _get_target_directory(self):
        if self._use_user_install():
            target = thonny.get_sys_path_directory_containg_plugins()
            os.makedirs(target, exist_ok=True)
            return self._normalize_target_path(target)
        else:
            for d in sys.path:
                if ("site-packages" in d or "dist-packages" in d) and path_startswith(
                    d, sys.prefix
                ):
                    return self._normalize_target_path(d)
            return None

    def _normalize_target_path(self, path: str) -> str:
        return normpath_with_actual_case(path)

    def _create_widgets(self, parent):
        banner = ttk.Frame(parent, style="Tip.TFrame")
        banner.grid(row=0, column=0, sticky="nsew")

        banner_msg = (
            tr(
                "This dialog is for managing Innovator plug-ins and their dependencies.\n"
                + "If you want to install packages for your own programs then choose 'Tools → Manage packages...'"
            )
            + "\n"
        )

        banner_msg += "\n" + tr(
            "NB! You need to restart Innovator after installing / upgrading / uninstalling a plug-in."
        )

        banner_text = ttk.Label(banner, text=banner_msg, style="Tip.TLabel", justify="left")
        banner_text.grid(pady=self.get_medium_padding(), padx=self.get_medium_padding())

        PipDialog._create_widgets(self, parent)

    def _get_title(self):
        return tr("Innovator plug-ins")

    def _run_pip_with_dialog(self, command: str, args: Dict, title: str) -> Tuple[int, str, str]:
        cmd = ["-m", "pip", "--disable-pip-version-check", "--no-color", command]
        if command == "install":
            cmd += [
                "--no-warn-script-location",
            ]
            if self._use_user_install():
                cmd += ["--user"]
        cmd += args

        proc = running.create_frontend_python_process(
            cmd,
            stderr=subprocess.STDOUT,
            environment_extras={"PYTHONUSERBASE": thonny.get_user_base_directory_for_plugins()},
        )
        dlg = SubprocessDialog(
            self, proc, title="pip " + command, long_description=title, autostart=True
        )
        ui_utils.show_dialog(dlg)
        return dlg.returncode, dlg.stdout, dlg.stderr


class DetailsDialog(CommonDialog):
    def __init__(self, master, package_metadata, selected_version, support_update_deps_switch):
        from distutils.version import StrictVersion

        assert isinstance(master, PipDialog)
        self._pip_dialog = cast(PipDialog, master)

        super().__init__(master)
        self.result = None
        self._closed = False
        self._version_data = None
        self._package_name = package_metadata["info"]["name"]
        self.title(tr("Advanced install / upgrade / downgrade"))

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        main_frame = ttk.Frame(self)  # To get styled background
        main_frame.grid(sticky="nsew")
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        version_label = ttk.Label(main_frame, text=tr("Desired version"))
        version_label.grid(
            row=0,
            column=0,
            columnspan=2,
            padx=self.get_medium_padding(),
            pady=(self.get_medium_padding(), 0),
            sticky="w",
        )

        def version_sort_key(s):
            # Trying to massage understandable versions into valid StrictVersions
            if s.replace(".", "").isnumeric():  # stable release
                s2 = s + "b999"  # make it latest beta version
            elif "rc" in s:
                s2 = s.replace("rc", "b8")
            else:
                s2 = s
            try:
                return StrictVersion(s2)
            except Exception:
                # use only numbers
                nums = re.findall(r"\d+", s)
                while len(nums) < 2:
                    nums.append("0")
                return StrictVersion(".".join(nums[:3]))

        version_strings = list(package_metadata["releases"].keys())
        version_strings.sort(key=version_sort_key, reverse=True)
        self.version_var = ui_utils.create_string_var(
            selected_version, self._start_fetching_version_info
        )
        self.version_combo = ttk.Combobox(
            main_frame, textvariable=self.version_var, values=version_strings, exportselection=False
        )

        self.version_combo.state(["!disabled", "readonly"])
        self.version_combo.grid(
            row=1,
            column=0,
            columnspan=2,
            pady=(0, self.get_medium_padding()),
            padx=self.get_medium_padding(),
            sticky="ew",
        )

        self.requires_label = ttk.Label(main_frame, text="")
        self.requires_label.grid(
            row=2,
            column=0,
            columnspan=2,
            pady=(0, self.get_medium_padding()),
            padx=self.get_medium_padding(),
            sticky="ew",
        )

        self.update_deps_var = tk.IntVar()
        self.update_deps_var.set(0)
        self.update_deps_cb = ttk.Checkbutton(
            main_frame, text=tr("Upgrade dependencies"), variable=self.update_deps_var
        )
        if support_update_deps_switch:
            self.update_deps_cb.grid(
                row=3, column=0, columnspan=2, padx=self.get_medium_padding(), sticky="w"
            )

        self.ok_button = ttk.Button(
            main_frame, text=master.get_install_button_text(), command=self._ok
        )
        self.ok_button.grid(
            row=4,
            column=0,
            pady=self.get_medium_padding(),
            padx=(self.get_medium_padding(), 0),
            sticky="se",
        )
        self.cancel_button = ttk.Button(main_frame, text=tr("Cancel"), command=self._cancel)
        self.cancel_button.grid(
            row=4,
            column=1,
            pady=self.get_medium_padding(),
            padx=(self.get_small_padding(), self.get_medium_padding()),
            sticky="se",
        )

        # self.resizable(height=tk.FALSE, width=tk.FALSE)
        self.version_combo.focus_set()

        self.bind("<Escape>", self._cancel, True)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        if self.version_var.get().strip():
            self._start_fetching_version_info()

    def _set_state(self, state):
        self._state = state
        widgets = [
            self.version_combo,
            # self.search_box, # looks funny when disabled
            self.ok_button,
            self.update_deps_cb,
        ]

        if state == "idle":
            self.config(cursor="")
            for widget in widgets:
                if widget == self.version_combo:
                    widget.state(["!disabled", "readonly"])
                else:
                    widget["state"] = tk.NORMAL
        else:
            self.config(cursor=get_busy_cursor())
            for widget in widgets:
                widget["state"] = tk.DISABLED

        if self.version_var.get().strip() == "" or not self._version_data:
            self.ok_button["state"] = tk.DISABLED

    def _start_fetching_version_info(self):
        self._set_state("busy")
        _start_fetching_package_info(
            self._package_name,
            url=self._pip_dialog._get_package_metadata_url(
                self._package_name, self.version_var.get()
            ),
            fallback_url=self._pip_dialog._get_package_metadata_fallback_url(
                self._package_name, self.version_var.get()
            ),
            completion_handler=self._show_version_info,
        )

    def _show_version_info(self, name, info, error_code=None):
        if self._closed:
            return

        self._version_data = info
        reqs = ""
        if (
            not error_code
            and "requires_dist" in info["info"]
            and isinstance(info["info"]["requires_dist"], list)
        ):
            deps = [d for d in info["info"]["requires_dist"] if not _EXTRA_MARKER_RE.match(d)]
            if deps:
                reqs = tr("Requires:") + "\n  * " + "\n  * ".join(deps)
        elif error_code:
            reqs = tr("Error code:") + " " + str(error_code)
            if "error" in info:
                reqs += "\n" + tr("Error:") + " " + info["error"]
        else:
            reqs = ""

        self.requires_label.configure(text=reqs)
        self._set_state("idle")

    def _ok(self, event=None):
        self.result = (self.version_var.get(), self._version_data, bool(self.update_deps_var.get()))
        self._closed = True
        self.destroy()

    def _cancel(self, event=None):
        self.result = None
        self._closed = True
        self.destroy()


def _fetch_url_future(url, fallback_url=None, timeout=10):
    from urllib.request import urlopen

    def load_url():
        try:
            with urlopen(url, timeout=timeout) as conn:
                return (conn, conn.read())
        except urllib.error.HTTPError as e:
            if e.code == 404 and fallback_url is not None:
                with urlopen(fallback_url, timeout=timeout) as conn:
                    return (conn, conn.read())
            else:
                raise

    from concurrent.futures.thread import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    return executor.submit(load_url)


def _get_latest_stable_version(version_strings):
    from distutils.version import LooseVersion

    versions = []
    for s in version_strings:
        if s.replace(".", "").isnumeric():  # Assuming stable versions have only dots and numbers
            versions.append(
                LooseVersion(s)
            )  # LooseVersion __str__ doesn't change the version string

    if len(versions) == 0:
        return None

    return str(sorted(versions)[-1])


def _ask_installation_details(master, data, selected_version, support_update_deps_switch):
    dlg = DetailsDialog(master, data, selected_version, support_update_deps_switch)
    ui_utils.show_dialog(dlg, master)
    return dlg.result


def _start_fetching_package_info(name, url: str, fallback_url: str, completion_handler):
    import urllib.error
    import urllib.parse

    url_future = _fetch_url_future(url=url, fallback_url=fallback_url)

    def poll_fetch_complete():
        import json

        if url_future.done():
            try:
                _, bin_data = url_future.result()
                raw_data = bin_data.decode("UTF-8")
                data = json.loads(raw_data)
                if "info" in data and "name" not in data["info"]:
                    # this is the case of micropython.org/pi
                    data["info"]["name"] = name

                completion_handler(name, data)
            except urllib.error.HTTPError as e:
                completion_handler(
                    name, {"info": {"name": name}, "error": str(e), "releases": {}}, e.code
                )
            except Exception as e:
                completion_handler(
                    name, {"info": {"name": name}, "error": str(e), "releases": {}}, e
                )
        else:
            get_workbench().after(200, poll_fetch_complete)

    poll_fetch_complete()


def _extract_pypi_search_results(html_data: str) -> List[Dict[str, str]]:
    from html.parser import HTMLParser

    def get_class(attrs):
        for name, value in attrs:
            if name == "class":
                return value

        return None

    class_prefix = "package-snippet__"

    class PypiSearchResultsParser(HTMLParser):
        def __init__(self, data):
            HTMLParser.__init__(self)
            self.results = []
            self.active_class = None
            self.feed(data)

        def handle_starttag(self, tag, attrs):
            if tag == "a" and get_class(attrs) == "package-snippet":
                self.results.append({})

            if tag in ("span", "p"):
                tag_class = get_class(attrs)
                if tag_class in ("package-snippet__name", "package-snippet__description"):
                    self.active_class = tag_class
                else:
                    self.active_class = None
            else:
                self.active_class = None

        def handle_data(self, data):
            if self.active_class is not None:
                att_name = self.active_class[len(class_prefix) :]
                self.results[-1][att_name] = data

        def handle_endtag(self, tag):
            self.active_class = None

    return PypiSearchResultsParser(html_data).results


def _extract_click_text(widget, event, tag):
    # http://stackoverflow.com/a/33957256/261181
    try:
        index = widget.index("@%s,%s" % (event.x, event.y))
        tag_indices = list(widget.tag_ranges(tag))
        for start, end in zip(tag_indices[0::2], tag_indices[1::2]):
            # check if the tag matches the mouse click index
            if widget.compare(start, "<=", index) and widget.compare(index, "<", end):
                return widget.get(start, end)
    except Exception:
        logger.exception("extracting click text")

    return None


def get_not_supported_translation():
    return tr("Package manager is not available for this interpreter")


def download_dist_data_from_pypi(name: str, version: Optional[str]) -> Dict:
    if version is None:
        url = "https://pypi.org/pypi/{}/json".format(urllib.parse.quote(name))
    else:
        url = "https://pypi.org/pypi/{}/{}/json".format(
            urllib.parse.quote(name), urllib.parse.quote(version)
        )

    logger.info("Downloading package info (%r, %r) from %s", name, version, url)

    return download_and_parse_json(url)


def load_plugin() -> None:
    def get_pip_gui_class():
        proxy = get_runner().get_backend_proxy()
        if proxy is None:
            return None
        pip_gui_class = proxy.get_pip_gui_class()
        return pip_gui_class

    def open_backend_pip_gui(*args):
        pg_class = get_pip_gui_class()
        if pg_class is None:
            showerror(tr("Not supported"), get_not_supported_translation())
            return

        if not get_runner().is_waiting_toplevel_command():
            showerror(
                tr("Not available"),
                tr("You need to stop your program before launching the package manager."),
                master=get_workbench(),
            )
            return

        pg = pg_class(get_workbench())
        ui_utils.show_dialog(pg)

    def open_backend_pip_gui_enabled():
        class_ = get_pip_gui_class()
        return class_ is not None

    def open_plugins_pip_gui(*args):
        pg = PluginsPipDialog(get_workbench())
        ui_utils.show_dialog(pg)

    get_workbench().add_command(
        "backendpipgui",
        "tools",
        tr("Manage packages..."),
        open_backend_pip_gui,
        tester=open_backend_pip_gui_enabled,
        group=80,
    )
    get_workbench().add_command(
        "pluginspipgui", "tools", tr("Manage plug-ins..."), open_plugins_pip_gui, group=180
    )

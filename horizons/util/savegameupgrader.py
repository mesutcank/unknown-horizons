# ###################################################
# Copyright (C) 2012 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

import os
import os.path
import json
import shutil
import tempfile

from horizons.util.python import decorators
from horizons.constants import VERSION
from horizons.util import DbReader

class SavegameUpgrader(object):
	"""The class that prepares saved games to be loaded by the current version."""

	def __init__(self, path):
		super(SavegameUpgrader, self).__init__()
		self.original_path = path
		self.using_temp = False
		self.final_path = None

	def _upgrade_to_rev49(self, db):
		db("CREATE TABLE \"resource_overview_bar\" (object INTEGER NOT NULL, position INTEGER NOT NULL, resource INTEGER NOT NULL)")

	def _upgrade_to_rev50(self, db):
		db("UPDATE stance set stance = \"hold_ground_stance\" where stance =\"hold_ground\"")
		db("UPDATE stance set stance = \"none_stance\" where stance =\"none\"")
		db("UPDATE stance set stance = \"flee_stance\" where stance =\"flee_stance\"")
		db("UPDATE stance set stance = \"aggressive_stance\" where stance =\"aggressive\"")

	def _upgrade_to_rev51(self, db):
		# add fire slot to settlers. Use direct numbers since only these work and they must never change.
		for (settler_id, ) in db("SELECT rowid FROM building WHERE type = ?", 3):
			db("INSERT INTO storage_slot_limit(object, slot, value) VALUES(?, ?, ?)",
			   settler_id, 42, 1)

	def _upgrade_to_rev52(self, db):
		# create empty disaster tables
		db('CREATE TABLE "disaster" ( type STRING NOT NULL, settlement INTEGER NOT NULL, remaining_ticks_expand INTEGER NOT NULL)')
		db('CREATE TABLE "fire_disaster" ( disaster INTEGER NOT NULL, building INTEGER NOT NULL, remaining_ticks_havoc INTEGER NOT NULL )')
		db('CREATE TABLE "disaster_manager" ( remaining_ticks INTEGER NOT NULL )')
		db('INSERT INTO "disaster_manager" VALUES(1)')

	def _upgrade_to_rev53(self, db):
		# convert old logbook (heading, message) tuples to new syntax, modify logbook table layout
		old_entries = db("SELECT heading, message FROM logbook")
		db('DROP TABLE logbook')
		db('CREATE TABLE logbook ( widgets string )')
		widgets = []
		for heading, message in old_entries:
			add = []
			add.append(['Headline', heading])
			add.append(['Image', "content/gui/images/background/hr.png"])
			add.append(['Label', message])
			widgets.append(add)
		db("INSERT INTO logbook(widgets) VALUES(?)", json.dumps(widgets))

	def _upgrade_to_rev54(self, db):
		for (settlement,) in db("SELECT DISTINCT settlement FROM settlement_level_properties WHERE level = ?", 0):
			db("INSERT INTO settlement_level_properties VALUES(?, 3, 0, 1)", settlement)

	def _upgrade_to_rev55(self, db):
		# The upgrade system has been mishandled, this upgrade tries to fix
		# as much as possible. It's partly brute force and might not work every
		# time, however the savegames are in an undefined state, so recovery is hard

		# make anything inflamable, the code should be able to handle it
		for (obj, ) in db("SELECT rowid FROM building where type != 8"):
			db("INSERT INTO storage_slot_limit (object, slot, value) VALUES (?, ?, ?)",
			   obj, 99, 1)

		# make farm be able to store grain and stuff
		for (obj, ) in db("SELECT rowid FROM building where type = 20"):
			db("INSERT INTO storage_slot_limit (object, slot, value) VALUES (?, ?, ?)",
			   obj, 43, 6)
			db("INSERT INTO storage_slot_limit (object, slot, value) VALUES (?, ?, ?)",
			   obj, 42, 6)

	def _upgrade_to_rev56(self, db):
		db("CREATE TABLE \"last_active_settlement\" ( type STRING NOT NULL, value INTEGER NOT NULL )")
		db("INSERT INTO last_active_settlement(type, value) VALUES(?, ?)", "LAST_NONE_FLAG", False)

	def _upgrade_to_rev57(self, db):
		"""Change storage of scenario variables from pickle to json."""
		import pickle
		db.connection.text_factory = str # need to read as str, utf-8 chokes on binary pickle

		for key, value in db("SELECT key, value FROM scenario_variables"):
			value = pickle.loads(value)
			value = json.dumps(value)
			db("UPDATE scenario_variables SET value = ? WHERE key = ?", value, key)

	def _upgrade(self):
		# fix import loop
		from horizons.savegamemanager import SavegameManager
		metadata = SavegameManager.get_metadata(self.original_path)
		rev = metadata['savegamerev']
		if rev == 0: # not a regular savegame, usually a map
			self.final_path = self.original_path
		elif rev == VERSION.SAVEGAMEREVISION: # the current version
			self.final_path = self.original_path
		else: # upgrade
			self.using_temp = True
			handle, self.final_path = tempfile.mkstemp(prefix='uh-savegame.' + os.path.basename(os.path.splitext(self.original_path)[0]) + '.', suffix='.sqlite')
			os.close(handle)
			shutil.copyfile(self.original_path, self.final_path)
			db = DbReader(self.final_path)
			db('BEGIN TRANSACTION')

			if rev < 49:
				self._upgrade_to_rev49(db)
			if rev < 50:
				self._upgrade_to_rev50(db)
			if rev < 51:
				self._upgrade_to_rev51(db)
			if rev < 52:
				self._upgrade_to_rev52(db)
			if rev < 53:
				self._upgrade_to_rev53(db)
			if rev < 54:
				self._upgrade_to_rev54(db)
			if rev < 55:
				self._upgrade_to_rev55(db)
			if rev < 56:
				self._upgrade_to_rev56(db)
			if rev < 57:
				self._upgrade_to_rev57(db)


			db('COMMIT')
			db.close()

	def get_path(self):
		"""Return the path to the up-to-date version of the saved game."""
		if self.final_path is None:
			self._upgrade()
		return self.final_path

	def close(self):
		if self.using_temp:
			self.using_temp = False
			os.unlink(self.final_path)
		self.final_path = None

decorators.bind_all(SavegameUpgrader)

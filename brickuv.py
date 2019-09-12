import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix

class Params:
	def __init__(self, texture_size, cell_size, rotate, offset, double_halves, coplanar, random, subdiv):
		self.texture_size = texture_size
		self.cell_size = cell_size
		self.rotate = rotate
		self.offset = offset
		self.double_halves = double_halves
		self.coplanar = coplanar
		self.random = random
		self.subdiv = subdiv

		self.subdivs = cell_size if subdiv else Vector((1, 1))

_islands = []
_params = None

def find_island(face):
	for i in _islands:
		if face in i.faces:
			return i
	return None

def increment_loop(loop, count):
	for i in range(count):
		loop = loop.link_loop_next
	return loop

class FaceGrid:
	class Item:
		def __init__(self, loop, x, y):
			self.loop = loop # Treat as bottom loop, y going upwards.
			self.x = x
			self.y = y

	def __init__(self, face):
		self.faces = set()
		self.items = []
		self.min_x = self.min_y = self.max_x = self.max_y = 0
		self.add_item(face, 0, 0)

		print('FaceGrid: width = %d, height = %d, faces = %d' % (1 + self.max_x - self.min_x, 1 + self.max_y - self.min_y, len(self.items)))

	def add_item(self, loop, x, y):
		if not loop.face.select:
			raise RuntimeError('Island.add_item: face not selected')

		item = FaceGrid.Item(loop, x, y)
		self.items.append(item)
		self.faces.add(loop.face)

		self.min_x = min(self.min_x, x)
		self.min_y = min(self.min_y, y)
		self.max_x = max(self.max_x, x)
		self.max_y = max(self.max_y, y)
		
		twin_adjust_loop = [2, 1, 0, 3]
		twin_delta_x = [0, 1, 0, -1]
		twin_delta_y = [-1, 0, 1, 0]
		
		for i in range(4):
			twin = loop.link_loop_radial_next
			if twin and twin.face.select:
				if not twin.face in self.faces:
					self.add_item(increment_loop(twin, twin_adjust_loop[i]), x + twin_delta_x[i], y + twin_delta_y[i])
			loop = loop.link_loop_next

class Cell:
	class Face:
		def __init__(self, loop, x, y):
			self.loop, self.x, self.y = loop, x, y

	def __init__(self):
		self.faces = []
		self.is_end = [False] * 4 # CCW from bottom.

class Island:
	def __init__(self, face):
		# Try to use loop with consistent orientation.
		best = face.loops[0]
		for i in range(1, 4):
			v = face.loops[i].vert.co
			b = best.vert.co
			if (v.z < b.z) or (v.z == b.z and v.y < b.y) or (v.z == b.z and v.y == b.y and v.x < b.x):
				best = face.loops[i]
	
		# Find contiguous faces and assign them to cells.
		grid = FaceGrid(best)
		self.faces = grid.faces
		self.width = 1 + grid.max_x - grid.min_x
		self.height = 1 + grid.max_y - grid.min_y
		self.rows = [[None] * self.width for i in range(self.height)]
		for item in grid.items:
			face_x = item.x - grid.min_x
			face_y = item.y - grid.min_y
			cell_x = face_x // int(_params.subdivs.x)
			cell_y = face_y // int(_params.subdivs.y)

			cell = self.rows[cell_y][cell_x]
			if not cell:
				cell = self.rows[cell_y][cell_x] = Cell()

			cell.faces.append(Cell.Face(item.loop, face_x % _params.subdivs.x, face_y % _params.subdivs.y))
			
		# Set cells border states.
		for y in range(self.height):
			for x in range(self.width):
				cell = self.rows[y][x]
				if cell:
					cell.is_end[0] = y == 0 or not self.rows[y - 1][x]
					cell.is_end[1] = x == self.width - 1 or not self.rows[y][x + 1]
					cell.is_end[2] = y == self.height - 1 or not self.rows[y + 1][x]
					cell.is_end[3] = x == 0 or not self.rows[y][x - 1]

	def get_uv(self, cell_x, cell_y, cell_width, face_x, face_y):
		u = (0.5 + (cell_x + cell_width * face_x / _params.subdivs.x) * _params.cell_size.x) / _params.texture_size.x
		v = (0.5 + (cell_y + face_y / _params.subdivs.y) * _params.cell_size.y) / _params.texture_size.y
		return (u, 1 - v)
	
	def get_texture_span(self, x, y, is_start_x, is_end_x):
		width = 1 
		if _params.double_halves:
			phase = (x + y + _params.offset) % 2 == 1
			if (is_start_x and is_end_x) or (is_start_x and phase) or (is_end_x and not phase):
				width += 1
				x -= 1 if phase else 0

		x += 1 if _params.offset else 0
		
		return x, y, width
	
	def apply(self, bm):
		uv_layer = bm.loops.layers.uv.verify()
		x_org = random.randrange(0, _params.texture_size.x // _params.cell_size.x, 2) if _params.random else 0
		y_org = random.randrange(0, _params.texture_size.y // _params.cell_size.y, 2) if _params.random else 0
		for y in range(self.height):
			for x in range(self.width):
				cell = self.rows[y][x]
				if cell:
					if _params.rotate:
						tex_x, tex_y, tex_width = self.get_texture_span(x_org + y, y_org + x, cell.is_end[0], cell.is_end[2])
					else:
						tex_x, tex_y, tex_width = self.get_texture_span(x_org + x, y_org + y, cell.is_end[3], cell.is_end[1])

					for face in cell.faces:
						loop = face.loop
						fx, fy = (face.y, face.x) if _params.rotate else (face.x, face.y)
						corners = [(fx, fy), (fx + 1, fy), (fx + 1, fy + 1), (fx, fy + 1)]
						for i in range(4):
							loop[uv_layer].uv = self.get_uv(tex_x, tex_y, tex_width, *corners[i])
							loop = loop.link_loop_prev if _params.rotate else loop.link_loop_next
		
def main(context, params):
	global _params, _islands
	_params = params
	_islands = []
	me = context.active_object.data
	bm = bmesh.from_edit_mesh(me)

	if params.coplanar:
		bpy.ops.mesh.select_similar(type='COPLANAR')

	for face in bm.faces:
		if face.select:
			if not find_island(face):
				_islands.append(Island(face))

	for i in _islands:
		i.apply(bm)

	bmesh.update_edit_mesh(me)

class BrickUvOperator(bpy.types.Operator):
	bl_idname = "brickuv.operator"
	bl_label = "Brick UV Operator"
	bl_options = {'REGISTER', 'UNDO'}

	texture_size_u: bpy.props.IntProperty(default = 128)
	texture_size_v: bpy.props.IntProperty(default = 128)
	cell_size_u: bpy.props.IntProperty(default = 8)
	cell_size_v: bpy.props.IntProperty(default = 8)
	rotate: bpy.props.BoolProperty(default = False)
	offset: bpy.props.BoolProperty(default = False)
	double_halves: bpy.props.BoolProperty(default = True)
	coplanar: bpy.props.BoolProperty(default = False)
	random: bpy.props.BoolProperty(default = True)
	subdiv: bpy.props.BoolProperty(default = False)

	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

	def execute(self, context):
		params = Params(Vector((self.texture_size_u, self.texture_size_v)), Vector((self.cell_size_u, self.cell_size_v)), self.rotate, self.offset, self.double_halves, self.coplanar, self.random, self.subdiv)
		main(context, params)
		return {'FINISHED'}

	def invoke(self, context, event):
		return self.execute(context)

def register():
	bpy.utils.register_class(BrickUvOperator)

def unregister():
	bpy.utils.unregister_class(BrickUvOperator)

if __name__ == "__main__":
	register()

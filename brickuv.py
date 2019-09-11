import bpy
import bmesh
import math
import random
from mathutils import Vector, Matrix

class Params:
	def __init__(self, texture_size, face_size, rotate, offset, double_halves, coplanar, random):
		self.texture_size = texture_size
		self.face_size = face_size
		self.rotate = rotate
		self.offset = offset
		self.double_halves = double_halves
		self.coplanar = coplanar
		self.random = random

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

class Item:
	def __init__(self, loop, x, y):
		self.loop = loop # Treat as bottom loop, y going upwards.
		self.x = x
		self.y = y
		self.has_neighbour = [False] * 4
			
class Island:
	def __init__(self, face):
		self.faces = set()
		self.items = []
		self.min_x = self.min_y = self.max_x = self.max_y = 0

		# Try to use loop with consistent orientation.
		best = face.loops[0]
		for i in range(1, 4):
			v = face.loops[i].vert.co
			b = best.vert.co
			if (v.z < b.z) or (v.z == b.z and v.y < b.y) or (v.z == b.z and v.y == b.y and v.x < b.x):
				best = face.loops[i]
		
		self.add_item(best, 0, 0)

		print('Island: width = %d, height = %d, faces = %d' % (1 + self.max_x - self.min_x, 1 + self.max_y - self.min_y, len(self.items)))
			
	def add_item(self, loop, x, y):
		if not loop.face.select:
			raise RuntimeError('Island.add_item: face not selected')

		item = Item(loop, x, y)
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
				item.has_neighbour[i] = True
				if not twin.face in self.faces:
					self.add_item(increment_loop(twin, twin_adjust_loop[i]), x + twin_delta_x[i], y + twin_delta_y[i])
			loop = loop.link_loop_next

	def get_uv(self, x, y):
		x += 1 if _params.offset else 0
		u = (0.5 + x * _params.face_size.x) / _params.texture_size.x
		v = (0.5 + y * _params.face_size.y) / _params.texture_size.y
		return (u, 1 - v)
	
	def get_face_uvs(self, x, y, is_start_x, is_end_x):
		left = x
		right = x + 1
		if _params.double_halves:
			phase = (x + y + _params.offset) % 2 == 1
			if (is_start_x and is_end_x) or (is_start_x and phase) or (is_end_x and not phase):
				if phase:
					left -= 1
				else:
					right += 1
		
		return [(left, y), (right, y), (right, y + 1), (left, y + 1)]
	
	def apply(self, bm):
		uv_layer = bm.loops.layers.uv.verify()
		x_org = random.randrange(0, _params.texture_size.x // _params.face_size.x, 2) if _params.random else 0
		y_org = random.randrange(0, _params.texture_size.y // _params.face_size.y, 2) if _params.random else 0
		for item in self.items:
			x, y = item.x - self.min_x, item.y - self.min_y
			if _params.rotate:
				corners = self.get_face_uvs(x_org + y, y_org + x, not item.has_neighbour[0], not item.has_neighbour[2]) 
			else:
				corners = self.get_face_uvs(x_org + x, y_org + y, not item.has_neighbour[3], not item.has_neighbour[1]) 
			
			loop = item.loop
			for i in range(4):
				loop[uv_layer].uv = self.get_uv(*corners[i])
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
	face_size_u: bpy.props.IntProperty(default = 8)
	face_size_v: bpy.props.IntProperty(default = 8)
	rotate: bpy.props.BoolProperty(default = False)
	offset: bpy.props.BoolProperty(default = False)
	double_halves: bpy.props.BoolProperty(default = True)
	coplanar: bpy.props.BoolProperty(default = False)
	random: bpy.props.BoolProperty(default = True)

	@classmethod
	def poll(cls, context):
		obj = context.active_object
		return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

	def execute(self, context):
		params = Params(Vector((self.texture_size_u, self.texture_size_v)), Vector((self.face_size_u, self.face_size_v)), self.rotate, self.offset, self.double_halves, self.coplanar, self.random)
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

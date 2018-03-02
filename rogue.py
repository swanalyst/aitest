import libtcodpy as libtcod
import math
import textwrap

SCREEN_WIDTH = 120
SCREEN_HEIGHT = 80
LIMIT_FPS = 20

LIGHTNING_RANGE = 5
LIGHTNING_MAX_DAMAGE = 5

MP_REGENERATION_INTERVAL = 10

MAP_WIDTH = 120
MAP_HEIGHT = 75

ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 50

FOV_ALGO = 0  #default FOV algorithm
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10

#sizes and coordinates relevant for the GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT


MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1

MAX_ROOM_MONSTERS = 3

MONSTER_GROUP_RANGE = 50

color_dark_wall = libtcod.Color(0, 0, 100)
color_light_wall = libtcod.Color(130, 110, 50)
color_dark_ground = libtcod.Color(50, 50, 150)
color_light_ground = libtcod.Color(200, 180, 50)

#create the list of game messages and their colors, starts empty
game_msgs = []

game_state = 'playing'
player_action = None
turn_counter = 0

class Fighter:
	#combat-related properties and methods (monster, player, NPC).
	def __init__(self, hp, defense, power, death_function=None):
		self.death_function = death_function		
		self.max_hp = hp
		self.hp = hp
		self.defense = defense
		self.power = power

	def take_damage(self, damage):
        #apply damage if possible
		if damage > 0:
			self.hp -= damage
       		#check for death. if there's a death function, call it
			if self.hp <= 0:
				function = self.death_function
				if function is not None:
					function(self.owner)				

	def attack(self, target):
        #a simple formula for attack damage
		damage = self.power - target.fighter.defense
 
		if damage > 0:
            #make the target take some damage
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.')
			target.fighter.take_damage(damage)
		else:
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect!')


class Mage:
	def __init__(self, mp):
		self.mp = mp
		self.max_mp = mp

	def cast_lightning(self):
		if self.mp <= 1:
			message('Not enough magic points.')
			return 'cancelled'
		message('Left-click an enemy to zap it, or right-click to cancel. (Range 2-4)', libtcod.light_cyan)
		monster = target_monster(LIGHTNING_RANGE)
		if monster is None:
			message('Canceled.')
			return 'cancelled'
 
    	#zap it!
		damage = 2*libtcod.random_get_int(0, 1, LIGHTNING_MAX_DAMAGE)    
		message('A lighting bolt strikes the ' + monster.name + ' with a loud thunder! The damage is '
			+ str(damage) + ' hit points.', libtcod.light_blue)
		monster.fighter.take_damage(damage)
		self.mp -= 2

	def regenerate(self):
		if self.mp < self.max_mp:
			self.mp += 1


class BasicMonster:
	#AI for a basic monster.
	def __init__(self):
		self.state = 'flocking'
		self.last_x = 0
		self.last_y = 0

	def take_turn(self):
        #a basic monster takes its turn. If you can see it, it can see you
		monster = self.owner
		if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
 
			self.state = 'chasing'
			self.last_x = player.x
			self.last_y = player.y

            #move towards player if far away
			if monster.distance_to(player) >= 2:
				monster.move_astar(player)
 
            #close enough, attack! (if the player is still alive.)
			elif player.fighter.hp > 0:
				monster.fighter.attack(player)	

		#Move towards last known player position, if no longer in FOV
		elif self.state == 'chasing':
			if monster.x == self.last_x and monster.y == self.last_y:
				self.state = 'flocking'
			else:
				monster.move_towards(self.last_x, self.last_y)

		#Default behaviour, flock into attack group with neighbouring monsters
		elif self.state == 'flocking':
			closest_dist = MONSTER_GROUP_RANGE
			closest_monster = None			
			for object in objects:
				if object.fighter and not object == player and not object == monster:
					dist = monster.distance_to(object)
					if dist < closest_dist:  #it's closer, so remember it
						closest_monster = object
						closest_dist = dist

			if closest_monster != None:
				if monster.distance_to(closest_monster) >= 2:
					monster.move_astar(closest_monster)
		

class Rect:
    #a rectangle on the map. used to characterize a room.
	def __init__(self, x, y, w, h):
		self.x1 = x
		self.y1 = y
		self.x2 = x + w
		self.y2 = y + h

	def center(self):
		center_x = (self.x1 + self.x2) / 2
		center_y = (self.y1 + self.y2) / 2
		return (center_x, center_y)
 
	def intersect(self, other):
        #returns true if this rectangle intersects with another one
		return (self.x1 <= other.x2 and self.x2 >= other.x1 and self.y1 <= other.y2 and self.y2 >= other.y1)



class Tile:
    #a tile of the map and its properties
	def __init__(self, blocked, block_sight = None):
		self.blocked = blocked
 
        #by default, if a tile is blocked, it also blocks sight
		if block_sight is None: block_sight = blocked
		self.block_sight = block_sight

class Object:
    #this is a generic object: the player, a monster, an item, the stairs...
    #it's always represented by a character on screen.
	def __init__(self, x, y, char, name, color, blocks=False, fighter=None, ai=None, mage=None):
		self.name = name
		self.blocks = blocks
		self.x = x
		self.y = y
		self.char = char
		self.color = color
		self.fighter = fighter
		if self.fighter:  #let the fighter component know who owns it
			self.fighter.owner = self
 
		self.ai = ai
		if self.ai:  #let the AI component know who owns it
			self.ai.owner = self	

		self.mage = mage
		if self.mage:  #let the mage component know who owns it
			self.mage.owner = self				
 
	def move(self, dx, dy):
        #move by the given amount
 		if not is_blocked(self.x + dx, self.y + dy):     
			self.x += dx
			self.y += dy
 
	def draw(self):
        #set the color and then draw the character that represents this object at its position
		if libtcod.map_is_in_fov(fov_map, self.x, self.y):
			libtcod.console_set_default_foreground(con, self.color)
			libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)
 
	def clear(self):
        #erase the character that represents this object
		libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)

	def move_towards(self, target_x, target_y):
        #vector from this object to the target, and distance
		dx = target_x - self.x
		dy = target_y - self.y
		distance = math.sqrt(dx ** 2 + dy ** 2)
 
        #normalize it to length 1 (preserving direction), then round it and
        #convert to integer so the movement is restricted to the map grid
		dx = int(round(dx / distance))
		dy = int(round(dy / distance))
		self.move(dx, dy)

	def distance_to(self, other):
        #return the distance to another object
		dx = other.x - self.x
		dy = other.y - self.y
		return math.sqrt(dx ** 2 + dy ** 2)

	def send_to_back(self):
        #make this object be drawn first, so all others appear above it if they're in the same tile.
		global objects
		objects.remove(self)
		objects.insert(0, self)		

	def move_astar(self, target):
		#Create a FOV map that has the dimensions of the map
		fov = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
 
        #Scan the current map each turn and set all the walls as unwalkable
		for y1 in range(MAP_HEIGHT):
			for x1 in range(MAP_WIDTH):
				libtcod.map_set_properties(fov, x1, y1, not map[x1][y1].block_sight, not map[x1][y1].blocked)
 
        #Scan all the objects to see if there are objects that must be navigated around
        #Check also that the object isn't self or the target (so that the start and the end points are free)
        #The AI class handles the situation if self is next to the target so it will not use this A* function anyway   
		for obj in objects:
			if obj.blocks and obj != self and obj != target:
                #Set the tile as a wall so it must be navigated around
				libtcod.map_set_properties(fov, obj.x, obj.y, True, False)
 
        #Allocate a A* path
        #The 1.41 is the normal diagonal cost of moving, it can be set as 0.0 if diagonal moves are prohibited
		my_path = libtcod.path_new_using_map(fov, 1.41)
 
        #Compute the path between self's coordinates and the target's coordinates
		libtcod.path_compute(my_path, self.x, self.y, target.x, target.y)
 
        #Check if the path exists, and in this case, also the path is shorter than 25 tiles
        #The path size matters if you want the monster to use alternative longer paths (for example through other rooms) if for example the player is in a corridor
        #It makes sense to keep path size relatively low to keep the monsters from running around the map if there's an alternative path really far away        
		if not libtcod.path_is_empty(my_path) and libtcod.path_size(my_path) < 25:
            #Find the next coordinates in the computed full path
			x, y = libtcod.path_walk(my_path, True)
			if x or y:
                #Set self's coordinates to the next path tile
				self.x = x
				self.y = y
		else:
            #Keep the old move function as a backup so that if there are no paths (for example another monster blocks a corridor)
            #it will still try to move towards the player (closer to the corridor opening)
			self.move_towards(target.x, target.y)  
 
        #Delete the path to free memory
		libtcod.path_delete(my_path)




def target_monster(max_range=None):
    #returns a clicked monster inside FOV up to a range, or None if right-clicked
	while True:
		(x, y) = target_tile(max_range)
		if x is None:  #player cancelled
			return None

        #return the first clicked monster, otherwise continue looping
		for obj in objects:     	
			if obj.x == x and obj.y == y and obj.fighter and obj != player:
				dist = player.distance_to(obj)   				
				if dist > max_range or dist <= 1:
					return None				
				else:
					return obj


def target_tile(max_range=None):
    #return the position of a tile left-clicked in player's FOV (optionally in a range), or (None,None) if right-clicked.
	global key, mouse   
	while True:
        #render the screen. this erases the inventory and shows the names of objects under the mouse.
		libtcod.console_flush()
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
		render_all()
 
		(x, y) = (mouse.cx, mouse.cy)
 
		if mouse.lbutton_pressed:
			return (x, y)
		elif mouse.rbutton_pressed:
			return (None, None)

def player_death(player):
    #the game ended!
	global game_state
	message('You died!')
	game_state = 'dead'
 
    #for added effect, transform the player into a corpse!
	player.char = '%'
	player.color = libtcod.dark_red
 

def message(new_msg, color = libtcod.white):
	#split the message if necessary, among multiple lines
	new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)
 
	for line in new_msg_lines:
        #if the buffer is full, remove the first line to make room for the new one
		if len(game_msgs) == MSG_HEIGHT:
			del game_msgs[0]
 
        #add the new line as a tuple, with the text and the color
		game_msgs.append( (line, color) )


	

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
	#render a bar (HP, experience, etc). first calculate the width of the bar
	bar_width = int(float(value) / maximum * total_width)
 
	#render the background first
	libtcod.console_set_default_background(panel, back_color)
	libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)
 
	#now render the bar on top
	libtcod.console_set_default_background(panel, bar_color)
	if bar_width > 0:
		libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)

	#finally, some centered text with the values
	libtcod.console_set_default_foreground(panel, libtcod.white)
	libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER, name + ': ' + str(value) + '/' + str(maximum))


def monster_death(monster):
    #transform it into a nasty corpse! it doesn't block, can't be
    #attacked and doesn't move
	message(monster.name.capitalize() + ' is dead!')
	monster.char = '%'
	monster.color = libtcod.dark_red
	monster.blocks = False
	monster.fighter = None
	monster.ai = None
	monster.name = 'remains of ' + monster.name
	monster.send_to_back()

def player_move_or_attack(dx, dy):
	global fov_recompute
	global turn_counter
 
	turn_counter += 1
	if turn_counter % MP_REGENERATION_INTERVAL == 0:
		player.mage.regenerate()

    #the coordinates the player is moving to/attacking
	x = player.x + dx
	y = player.y + dy
 
    #try to find an attackable object there
	target = None
	for object in objects:
		if object.fighter and object.x == x and object.y == y:
			target = object
			break
 
    #attack if target found, move otherwise
	if target is not None:
		player.fighter.attack(target)
	else:
		player.move(dx, dy)
		fov_recompute = True


def is_blocked(x, y):
    #first test the map tile
	if map[x][y].blocked:
		return True
 
    #now check for any blocking objects
	for object in objects:
		if object.blocks and object.x == x and object.y == y:
			return True
 
 	return False

def create_room(room):
    global map
    #go through the tiles in the rectangle and make them passable
    for x in range(room.x1 + 1, room.x2):
        for y in range(room.y1 + 1, room.y2):
            map[x][y].blocked = False
            map[x][y].block_sight = False

def place_objects(room):
    #choose random number of monsters
	num_monsters = libtcod.random_get_int(0, 0, MAX_ROOM_MONSTERS)
 
	for i in range(num_monsters):
        #choose random spot for this monster
		x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
		y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
		if not is_blocked(x, y):
			if libtcod.random_get_int(0, 0, 100) < 80:  #80% chance of getting an orc
            #create an orc
				fighter_component = Fighter(hp=10, defense=0, power=3, death_function=monster_death)
				ai_component = BasicMonster()            
				monster = Object(x, y, 'o', 'orc', libtcod.desaturated_green, blocks=True, fighter=fighter_component, ai=ai_component)
			else:
            #create a troll
				fighter_component = Fighter(hp=16, defense=1, power=4, death_function=monster_death)
				ai_component = BasicMonster()

				monster = Object(x, y, 'T', 'troll', libtcod.darker_green, blocks=True, fighter=fighter_component, ai=ai_component)
 
			objects.append(monster)

def get_names_under_mouse():
	global mouse
 
    #return a string with the names of all objects under the mouse
	(x, y) = (mouse.cx, mouse.cy)

	#create a list with the names of all objects at the mouse's coordinates and in FOV
	names = [obj.name for obj in objects
		if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]	

	names = ', '.join(names)  #join the names, separated by commas
	return names.capitalize()


def handle_keys(): 
	global fov_recompute
	global key
	global player

	#key = libtcod.console_wait_for_keypress(True)
	if key.vk == libtcod.KEY_ENTER and key.lalt:
        #Alt+Enter: toggle fullscreen
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
 
	elif key.vk == libtcod.KEY_ESCAPE:
		return 'exit'  #exit game

	if game_state == 'playing':
        #movement keys
    #movement keys
		if key.vk ==libtcod.KEY_UP:
			player_move_or_attack(0, -1)
			fov_recompute = True		
 
		elif key.vk ==libtcod.KEY_DOWN:
			player_move_or_attack(0, 1)
			fov_recompute = True		
 
		elif key.vk ==libtcod.KEY_LEFT:
			player_move_or_attack(-1, 0)
			fov_recompute = True		
 
		elif key.vk ==libtcod.KEY_RIGHT:
			player_move_or_attack(1, 0)
			fov_recompute = True	

		elif key.vk ==libtcod.KEY_BACKSPACE or key.vk ==libtcod.KEY_DELETE:
			player.mage.cast_lightning()
			fov_recompute = True			

		else:
			return 'didnt-take-turn'				

def make_map():
	global map
 
    #fill map with "blocked" tiles
	map = [[ Tile(True)
		for y in range(MAP_HEIGHT) ]
			for x in range(MAP_WIDTH) ]
 
    #create two rooms
	rooms = []
	num_rooms = 0
 
 	for r in range(MAX_ROOMS):
        #random width and height
		w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
		h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        #random position without going out of the boundaries of the map
		x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
		y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)

		new_room = Rect(x, y, w, h)
 
        #run through the other rooms and see if they intersect with this one
		failed = False
		for other_room in rooms:
			if new_room.intersect(other_room):
				failed = True
				break
		if not failed:
            #this means there are no intersections, so this room is valid
 
            #"paint" it to the map's tiles
			create_room(new_room)
 
            #center coordinates of new room, will be useful later
			(new_x, new_y) = new_room.center()
 
			if num_rooms == 0:
                #this is the first room, where the player starts at
				player.x = new_x
				player.y = new_y
			else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel
 
                #center coordinates of previous room
				(prev_x, prev_y) = rooms[num_rooms-1].center()
 
                #draw a coin (random number that is either 0 or 1)
				if libtcod.random_get_int(0, 0, 1) == 1:
                    #first move horizontally, then vertically
					create_h_tunnel(prev_x, new_x, prev_y)
					create_v_tunnel(prev_y, new_y, new_x)
				else:
                    #first move vertically, then horizontally
					create_v_tunnel(prev_y, new_y, prev_x)
					create_h_tunnel(prev_x, new_x, new_y)
 
			#add some contents to this room, such as monsters
			place_objects(new_room)

            #finally, append the new room to the list
			rooms.append(new_room)
			num_rooms += 1


def create_h_tunnel(x1, x2, y):
    global map
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False


def create_v_tunnel(y1, y2, x):
    global map
    #vertical tunnel
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False        	
 
def render_all():
	global color_light_wall
	global color_light_ground
	global fov_recompute	

	if fov_recompute:
        #recompute FOV if needed (the player moved or something)
		fov_recompute = False
		libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)    
 
    #go through all tiles, and set their background color
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			visible = libtcod.map_is_in_fov(fov_map, x, y)        	
			wall = map[x][y].block_sight            
			if not visible:
				if wall:
					libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET )
				else:
					libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET )
			else:
 				#it's visible
				if wall:
					libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET )
				else:
					libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET )					 
    #draw all objects in the list
	for object in objects:
		object.clear()

	for object in objects:
		if object != player:		
			object.draw()
	player.draw()

    #blit the contents of "con" to the root console
	libtcod.console_blit(con, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, 0, 0)


	#prepare to render the GUI panel
	libtcod.console_set_default_background(panel, libtcod.black)
	libtcod.console_clear(panel)

    #print the game messages, one line at a time
	y = 1
	for (line, color) in game_msgs:
		libtcod.console_set_default_foreground(panel, color)
		libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
		y += 1		
 
    #show the player's stats
	render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp,libtcod.light_red, libtcod.darker_red)

	render_bar(1, 3, BAR_WIDTH, 'MP', player.mage.mp, player.mage.max_mp,libtcod.light_blue, libtcod.darker_blue)

	#display names of objects under the mouse
	libtcod.console_set_default_foreground(panel, libtcod.light_gray)
	libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())

    #blit the contents of "panel" to the root console
	libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)

libtcod.console_set_custom_font('arial10x10.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'python/libtcod tutorial', False)
con = libtcod.console_new(SCREEN_WIDTH, SCREEN_HEIGHT)
libtcod.sys_set_fps(LIMIT_FPS)

fighter_component = Fighter(hp=30, defense=2, power=3, death_function=player_death)
mage_component = Mage(mp=20)
player = Object(0, 0, '@', 'player', libtcod.white, blocks=True, fighter=fighter_component, mage=mage_component)
#player.x = 25
#player.y = 23
#npc = Object(SCREEN_WIDTH/2 - 5, SCREEN_HEIGHT/2, '@', libtcod.yellow)
objects = [player]

make_map()

fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
for y in range(MAP_HEIGHT):
    for x in range(MAP_WIDTH):
        libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)

fov_recompute = True

panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)

message('Welcome stranger! Prepare to perish in the Tombs of the Ancient Kings.', libtcod.white)
message('Press Backspace or Del to hurl mighty lightning bolts..', libtcod.white)


mouse = libtcod.Mouse()
key = libtcod.Key()

libtcod.sys_set_fps(50)

render_all()
libtcod.console_flush()	

counter = 0

while not libtcod.console_is_window_closed():


	libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)	

	for object in objects:
		object.clear()

	player_action = handle_keys()
	if player_action == 'exit':
		break

	for object in objects:
		object.clear()

	if game_state == 'playing' and player_action != 'didnt-take-turn':
		for object in objects:
			if object.ai:
				object.ai.take_turn()

	render_all()
	libtcod.console_flush()					


from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import math
import random
import time
import sys

# ---- Constants ----
WINDOW_W = 1000
WINDOW_H = 800
GRID_LENGTH = 600
PLAYER_SIZE = 40
BULLET_SPEED = 10
MAX_BULLETS = 5
ENEMY_BASE_RADIUS = 30
ENEMY_RADIUS = ENEMY_BASE_RADIUS
ENEMY_RESPAWN_DELAY = 1.0
BOUNDARY_HEIGHT = 120
BULLET_RADIUS = 6
CAMERA_DISTANCE = 120
CAMERA_HEIGHT = 50
MOUSE_SENS = 0.18
PLAYER_MOVE_BASE = 1.1
TICKS_PER_SEC = 60

# Health/lives
PLAYER_MAX_HEALTH = 6
PLAYER_START_HEALTH = 3

# Difficulty progression
BASE_ZOMBIE_NUM = 5
ZOMBIE_SPEED_STEP_KILLS = 10
ZOMBIE_NUM_STEP_KILLS = 30
LEVEL_UP_EVERY = 10
LIFE_AWARD_EVERY_LEVELS = 3

# Alpha zombie
ALPHA_ZOMBIE_CHANCE = 5
ALPHA_ZOMBIE_SPEED_MULT = 2.7
ALPHA_ZOMBIE_SIZE_MULT = 1.5

MAX_MISSED_SHOTS = 100
HEALTH_PICKUP_DURATION = 10.0
BARRIER_COUNT = 12

class GameState:
    def __init__(self):
        self.player_pos = [0.0, 0.0, 30.0]
        self.player_angle = 0.0
        self.player_move_angle = 0.0
        self.bullets = []
        self.enemies = []
        self.score = 0
        self.health = PLAYER_START_HEALTH
        self.missed_shots = 0
        self.game_over = False
        self.cheat_mode = False
        self.camera_mode = 0
        self.hit_effects = []
        self.last_shot_time = 0
        self.auto_fire_delay = 0.15
        self.last_enemy_kill_time = 0
        self.zombie_count = BASE_ZOMBIE_NUM
        self.zombie_speed = 0.11
        self.level = 1
        self.hit_time = 0
        self.move_dir = [0, 0] # WASD: [X,Y]
        self.frame_time = time.time()
        self.delta_accum = 0

        # Health/AlphaZ Content
        self.health_pickup = None
        self.has_alpha_zombie = False
        self.alpha_zombie_killed = False
        self.rounds_since_alpha = 0
        self.arm_sway = 0
        self.arm_sway_dir = 1

game = GameState()


# --- Health pickup ---
class HealthPickup:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.z = 20  # Floating height
        self.rotation = 0
        self.spawn_time = time.time()
        self.pulse = 0
        self.pulse_dir = 1

    def update(self):
        self.rotation += 2
        self.pulse += 0.05 * self.pulse_dir
        if self.pulse > 1.0:
            self.pulse = 1.0
            self.pulse_dir = -1
        elif self.pulse < 0.0:
            self.pulse = 0.0
            self.pulse_dir = 1
        dx = game.player_pos[0] - self.x
        dy = game.player_pos[1] - self.y
        dist = math.hypot(dx, dy)
        if dist < PLAYER_SIZE:
            game.health = min(PLAYER_MAX_HEALTH, game.health + 1)
            return False
        if time.time() - self.spawn_time > HEALTH_PICKUP_DURATION:
            return False
        return True

# --- Zombie Enemy ---
class Zombie:
    def __init__(self, speed_min, speed_max, is_alpha=False):
        while True:
            dist = random.uniform(400, 1.2*GRID_LENGTH) 
            angle = random.uniform(0, 2*math.pi)
            self.x = dist * math.cos(angle)
            self.y = dist * math.sin(angle)
            if math.sqrt(self.x**2 + self.y**2) > 220:
                break
        self.z = ENEMY_RADIUS
        self.is_alpha = is_alpha
        if is_alpha:
            self.base_speed = random.uniform(speed_min, speed_max) * ALPHA_ZOMBIE_SPEED_MULT
            self.radius = ENEMY_RADIUS * ALPHA_ZOMBIE_SIZE_MULT
            self.body_col = (
                0.6 + 0.1*random.random(), 
                0.1 + 0.1*random.random(),
                0.1 + 0.05*random.random()
            )
            self.eye_col = (0.3, 0.9, 0.3)
        else:
            self.base_speed = random.uniform(speed_min * 0.5, speed_max * 0.5)
            self.radius = ENEMY_RADIUS
            self.body_col = (
                0.33 + 0.1*random.random(), 
                0.07 + 0.05*random.random(),
                0.08 + 0.05*random.random()
            )
            self.eye_col = (1.0, 0.1 + 0.3*random.random(), 0.1)
        self.speed = self.base_speed
        self.arm_sway = 0
        self.arm_sway_dir = 1
        self.head_bob = 0
        self.head_bob_dir = 1
        self.leg_angle = 0

    def update(self):
        dx = game.player_pos[0] - self.x
        dy = game.player_pos[1] - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            step = min(self.speed, dist)
            self.x += (dx/dist) * step
            self.y += (dy/dist) * step

            # Animation
            self.leg_angle = (self.leg_angle + self.speed * 8) % 360
            self.arm_sway += 0.1 * self.arm_sway_dir
            if abs(self.arm_sway) > 1:
                self.arm_sway_dir *= -1
            self.head_bob += 0.05 * self.head_bob_dir
            if abs(self.head_bob) > 0.5:
                self.head_bob_dir *= -1

        # Player collision (returns False if killed/should be removed)
        collision_radius = self.radius
        if not game.game_over:
            if dist < PLAYER_SIZE * 0.62 + collision_radius:
                now = time.time()
                if now - game.hit_time > 0.7:
                    # Only lose health and get game over if NOT in cheat mode
                    if not game.cheat_mode:
                        game.health -= 1
                        game.hit_time = now
                        print(f"Player HIT! Health now: {game.health}")
                        if game.health <= 0:
                            game.health = 0
                            game.game_over = True
                            print("GAME OVER! Player has died.")
                    # Always give alpha health pickup when hit, even in cheat mode
                    if self.is_alpha:
                        game.alpha_zombie_killed = True
                        game.health_pickup = HealthPickup(self.x, self.y)
                return False
        return True

# --- Bullet ---
class Bullet:
    def __init__(self, x, y, z, angle):
        self.x, self.y, self.z = x, y, z
        self.angle = angle
        self.lifetime = 100

    def update(self):
        prev_x, prev_y = self.x, self.y
        self.x += BULLET_SPEED * math.sin(math.radians(self.angle))
        self.y += BULLET_SPEED * math.cos(math.radians(self.angle))
        self.lifetime -= 1
        # Wall collision
        if (abs(self.x) > GRID_LENGTH-14) or (abs(self.y) > GRID_LENGTH-14):
            hit_x = max(min(self.x, GRID_LENGTH-14), -GRID_LENGTH+14)
            hit_y = max(min(self.y, GRID_LENGTH-14), -GRID_LENGTH+14)
            game.hit_effects.append(HitEffect(hit_x, hit_y, self.z))
            game.missed_shots += 1
            return False
        return self.lifetime > 0

# --- Blood/HitFX ---
class HitEffect:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
        self.lifetime = 16
        self.size = 11
        self.color = (0.87, 0.1, 0.1, 0.6 + 0.4*random.random())

    def update(self):
        self.lifetime -= 1
        return self.lifetime > 0
    
# ------- Drawing Helpers -------

def draw_zombies():
    glDisable(GL_LIGHTING)
    for z in game.enemies:
        # Torso
        glPushMatrix()
        glTranslatef(z.x, z.y, z.z)
        glColor3f(*z.body_col)
        torso_scale = (1.2, 0.8, 1.5) if not z.is_alpha else (1.4, 1.0, 1.8)
        glScalef(z.radius*torso_scale[0], z.radius*torso_scale[1], z.radius*torso_scale[2])
        glutSolidCube(1)
        glPopMatrix()

        # Legs
        for dx in [-1, 1]:
            glPushMatrix()
            glTranslatef(z.x + dx*z.radius*0.3, z.y, z.z - z.radius*0.5)
            leg_swing = math.sin(math.radians(z.leg_angle + (180 if dx > 0 else 0))) * 30
            glRotatef(leg_swing, 1, 0, 0)
            glColor3f(0.22, 0.11, 0.12)
            glScalef(z.radius*0.3, z.radius*0.3, z.radius*0.8)
            glutSolidCube(1)
            glPopMatrix()

        # Arms
        for dx in [-1, 1]:
            glPushMatrix()
            glTranslatef(z.x + dx*z.radius*0.9, z.y, z.z + z.radius*0.3)
            arm_angle = math.sin(z.arm_sway * 2 + (math.pi if dx > 0 else 0)) * 25
            glRotatef(arm_angle, 1, 0, 0)
            glRotatef(45 * dx, 0, 1, 0)
            glColor3f(0.2, 0.1, 0.1)
            glScalef(z.radius*0.2, z.radius*0.2, z.radius*0.9)
            glutSolidCube(1)
            glPopMatrix()

        # Head
        glPushMatrix()
        glTranslatef(z.x, z.y, z.z + z.radius*1.1 + z.head_bob)
        glColor3f(0.49, 0.51, 0.41)
        head_turn = math.atan2(game.player_pos[1] - z.y, game.player_pos[0] - z.x)
        glRotatef(math.degrees(head_turn), 0, 0, 1)
        if z.is_alpha:
            glScalef(1.2, 1.2, 1.2)
            glutSolidSphere(z.radius*0.5, 16, 16)
            for horn_angle in [45, -45]:
                glPushMatrix()
                glRotatef(horn_angle, 0, 1, 0)
                glTranslatef(0, 0, z.radius*0.4)
                glColor3f(0.3, 0.1, 0.1)
                glutSolidCone(z.radius*0.1, z.radius*0.4, 8, 8)
                glPopMatrix()
        else:
            glutSolidSphere(z.radius*0.5, 13, 13)
        glPopMatrix()

        # Eyes
        for sign in [-1, 1]:
            glPushMatrix()
            eye_x = z.x + sign*z.radius*0.2
            eye_y = z.y + z.radius*0.1
            eye_z = z.z + z.radius*1.2 + z.head_bob
            eye_dir = math.atan2(game.player_pos[1] - eye_y, game.player_pos[0] - eye_x)
            eye_adjustment_x = math.cos(eye_dir) * z.radius*0.05
            eye_adjustment_y = math.sin(eye_dir) * z.radius*0.05
            glTranslatef(eye_x + eye_adjustment_x, eye_y + eye_adjustment_y, eye_z)
            glColor3f(*z.eye_col)
            if z.is_alpha:
                glScalef(1.3, 1.3, 1.3)
                glutSolidSphere(z.radius*0.08, 8, 8)
                glColor4f(z.eye_col[0], z.eye_col[1], z.eye_col[2], 0.3)
                glutSolidSphere(z.radius*0.12, 8, 8)
            else:
                glutSolidSphere(z.radius*0.08, 6, 6)
            glPopMatrix()
    glEnable(GL_LIGHTING)

def draw_hit_effects():
    glDisable(GL_LIGHTING)
    for effect in game.hit_effects:
        glPushMatrix()
        glTranslatef(effect.x, effect.y, effect.z)
        intensity = effect.lifetime / 16.0
        glColor4f(*effect.color[:3], intensity*effect.color[3])
        glutSolidSphere(effect.size * (1 + 0.4 * (1 - intensity)), 8, 8)
        glPopMatrix()
    glEnable(GL_LIGHTING)

def draw_health_pickup():
    if not game.health_pickup: return
    glDisable(GL_LIGHTING)
    glPushMatrix()
    glTranslatef(game.health_pickup.x, game.health_pickup.y, game.health_pickup.z)
    glRotatef(game.health_pickup.rotation, 0, 0, 1)
    pulse = 1.0 + game.health_pickup.pulse * 0.3
    glColor3f(0.9, 0.9, 0.9)
    glScalef(15 * pulse, 15 * pulse, 8 * pulse)
    glutSolidCube(1)
    # Cross
    glColor3f(0.9, 0.1, 0.1)
    glPushMatrix()
    glTranslatef(0, 0, 0.1)
    glScalef(0.8, 0.25, 1.1)
    glutSolidCube(1)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, 0, 0.1)
    glScalef(0.25, 0.8, 1.1)
    glutSolidCube(1)
    glPopMatrix()
    glPopMatrix()
    # Glow aura
    glPushMatrix()
    glTranslatef(game.health_pickup.x, game.health_pickup.y, game.health_pickup.z)
    glRotatef(game.health_pickup.rotation*0.7, 0, 0, 1)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glColor4f(0.9, 0.2, 0.2, 0.3 * game.health_pickup.pulse)
    glutSolidSphere(17 * pulse, 16, 16)
    glDisable(GL_BLEND)
    glPopMatrix()
    glEnable(GL_LIGHTING)

def draw_player():
    glDisable(GL_LIGHTING)
    glPushMatrix()
    glTranslatef(*game.player_pos)
    glRotatef(game.player_angle, 0, 0, 1)
    move_bob = 0
    if any(game.move_dir):
        move_bob = math.sin(time.time() * 8) * 2

    # Legs
    leg_width = PLAYER_SIZE * 0.2
    leg_height = PLAYER_SIZE * 0.5
    for side in [-1, 1]:
        glPushMatrix()
        leg_offset = PLAYER_SIZE * 0.2 * side
        if any(game.move_dir):
            leg_swing = math.sin(time.time() * 8 + (math.pi if side > 0 else 0)) * 15
            glRotatef(leg_swing, 1, 0, 0)
        glTranslatef(leg_offset, 0, -PLAYER_SIZE * 0.4)
        glColor3f(0.1, 0.1, 0.3)
        glScalef(leg_width, leg_width, leg_height)
        glutSolidCube(1)
        glPopMatrix()

    # Torso
    glPushMatrix()
    glColor3f(0.3, 0.3, 0.35)
    glScalef(PLAYER_SIZE * 1.0, PLAYER_SIZE * 0.6, PLAYER_SIZE * 0.5)
    glutSolidCube(1)
    glPushMatrix()
    glTranslatef(0, 0, 0.1)
    glColor3f(0.4, 0.4, 0.45)
    glScalef(0.9, 0.9, 1.1)
    glutSolidCube(1)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, 0, 0.2)
    glColor3f(0.1, 0.7, 0.9)
    glScalef(0.3, 0.3, 1.1)
    glutSolidCube(1)
    glPopMatrix()
    glPopMatrix()

    # Shoulders
    for side in [-1, 1]:
        glPushMatrix()
        shoulder_x = PLAYER_SIZE * 0.5 * side
        glTranslatef(shoulder_x, 0, PLAYER_SIZE * 0.1)
        glColor3f(0.35, 0.35, 0.4)
        glutSolidSphere(PLAYER_SIZE * 0.25, 12, 12)
        glPopMatrix()

    # Arms
    for side in [-1, 1]:
        glPushMatrix()
        arm_x = PLAYER_SIZE * 0.5 * side
        if any(game.move_dir):
            arm_swing = math.sin(time.time() * 8 + (math.pi if side < 0 else 0)) * 15
            glTranslatef(arm_x, 0, 0)
            glRotatef(arm_swing, 1, 0, 0)
        else:
            glTranslatef(arm_x, 0, 0)
        glColor3f(0.3, 0.3, 0.35)
        glPushMatrix()
        glTranslatef(0, 0, -PLAYER_SIZE * 0.2)
        glScalef(PLAYER_SIZE * 0.2, PLAYER_SIZE * 0.2, PLAYER_SIZE * 0.4)
        glutSolidCube(1)
        glPopMatrix()
        glPopMatrix()

    # Head
    glPushMatrix()
    glTranslatef(0, 0, PLAYER_SIZE * 0.4 + move_bob * 0.3)
    glColor3f(0.6, 0.5, 0.4)
    glutSolidSphere(PLAYER_SIZE * 0.2, 16, 16)
    glPushMatrix()
    glColor3f(0.25, 0.25, 0.3)
    glScalef(1.1, 1.1, 0.9)
    glutSolidSphere(PLAYER_SIZE * 0.2, 16, 16)
    glPushMatrix()
    glTranslatef(0, PLAYER_SIZE * 0.12, 0)
    glColor3f(0.2, 0.8, 1.0)
    glScalef(PLAYER_SIZE * 0.3, PLAYER_SIZE * 0.1, PLAYER_SIZE * 0.15)
    glutSolidCube(1)
    glPopMatrix()
    glPopMatrix()
    glPopMatrix()

    # Gun
    glPushMatrix()
    glTranslatef(0, PLAYER_SIZE * 0.7, 0)
    glColor3f(0.2,0.2,0.2)
    glPushMatrix()
    glScalef(PLAYER_SIZE * 0.2, PLAYER_SIZE * 0.9, PLAYER_SIZE * 0.2)
    glutSolidCube(1)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, PLAYER_SIZE * 0.5, 0)
    glColor3f(0.1, 0.1, 0.1)
    glutSolidCylinder(PLAYER_SIZE * 0.15, PLAYER_SIZE * 0.1, 12, 4)
    glPopMatrix()
    for offset in [-0.3, -0.1, 0.1, 0.3]:
        glPushMatrix()
        glTranslatef(0, PLAYER_SIZE * offset, 0)
        glColor3f(0.3, 0.3, 0.3)
        glutSolidTorus(PLAYER_SIZE * 0.03, PLAYER_SIZE * 0.12, 12, 12)
        glPopMatrix()
    glPushMatrix()
    glTranslatef(0, -PLAYER_SIZE * 0.1, 0)
    glColor3f(0.4, 0.4, 0.4)
    glScalef(PLAYER_SIZE * 0.3, PLAYER_SIZE * 0.4, PLAYER_SIZE * 0.25)
    glutSolidCube(1)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, -PLAYER_SIZE * 0.3, -PLAYER_SIZE * 0.2)
    glRotatef(60, 1, 0, 0)
    glColor3f(0.15, 0.15, 0.15)
    glScalef(PLAYER_SIZE * 0.15, PLAYER_SIZE * 0.3, PLAYER_SIZE * 0.1)
    glutSolidCube(1)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, 0, -PLAYER_SIZE * 0.3)
    glColor3f(0.7, 0.7, 0)
    glScalef(PLAYER_SIZE * 0.2, PLAYER_SIZE * 0.3, PLAYER_SIZE * 0.1)
    glutSolidCube(1)
    glColor3f(0.9, 0.9, 0.2)
    glScalef(0.8, 0.8, 1.2)
    glutSolidCube(1)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, PLAYER_SIZE * 0.2, PLAYER_SIZE * 0.25)
    glColor3f(0.1, 0.1, 0.1)
    glScalef(PLAYER_SIZE * 0.1, PLAYER_SIZE * 0.2, PLAYER_SIZE * 0.1)
    glutSolidCube(1)
    glPushMatrix()
    glTranslatef(0, PLAYER_SIZE * 0.5, 0)
    glColor3f(0.2, 0.6, 1.0)
    glutSolidSphere(PLAYER_SIZE * 0.05, 8, 8)
    glPopMatrix()
    glPopMatrix()
    glPopMatrix()
    glPopMatrix()
    glEnable(GL_LIGHTING)

def draw_bullets():
    glDisable(GL_LIGHTING)
    for bullet in game.bullets:
        glPushMatrix()
        glTranslatef(bullet.x, bullet.y, bullet.z)
        glColor3f(0.90, 0.90, 0.10)
        glutSolidSphere(BULLET_RADIUS, 10, 10)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        trail_x = -math.sin(math.radians(bullet.angle)) * 3
        trail_y = -math.cos(math.radians(bullet.angle)) * 3
        for i in range(5):
            alpha = 0.7 - (i * 0.15)
            scale = 0.9 - (i * 0.15)
            glColor4f(0.9, 0.8, 0.0, alpha)
            glPushMatrix()
            glTranslatef(trail_x * i, trail_y * i, 0)
            glutSolidSphere(BULLET_RADIUS * scale, 8, 8)
            glPopMatrix()
        glDisable(GL_BLEND)
        glPopMatrix()
    glEnable(GL_LIGHTING)

# Draw the ground grid and arena features
def draw_grid():
    glDisable(GL_LIGHTING)
    square_size = 90
    for x in range(-int(GRID_LENGTH//square_size), int(GRID_LENGTH//square_size)):
        for y in range(-int(GRID_LENGTH//square_size), int(GRID_LENGTH//square_size)):
            if (x + y) % 2 == 0:
                glColor3f(0.22, 0.06, 0.08)
            else:
                glColor3f(0.14, 0.01, 0.10)
            glBegin(GL_QUADS)
            glVertex3f(x * square_size, y * square_size, 0)
            glVertex3f((x+1) * square_size, y * square_size, 0)
            glVertex3f((x+1) * square_size, (y+1) * square_size, 0)
            glVertex3f(x * square_size, (y+1) * square_size, 0)
            glEnd()
    glColor3f(0.47, 0.05, 0.10)
    glBegin(GL_LINE_LOOP)
    glVertex3f(-GRID_LENGTH, -GRID_LENGTH, 0)
    glVertex3f(GRID_LENGTH, -GRID_LENGTH, 0)
    glVertex3f(GRID_LENGTH, GRID_LENGTH, 0)
    glVertex3f(-GRID_LENGTH, GRID_LENGTH, 0)
    glEnd()
    glEnable(GL_LIGHTING)

def draw_boundaries():
    glDisable(GL_LIGHTING)
    wall_height = BOUNDARY_HEIGHT
    for i in range(BARRIER_COUNT):
        angle = (i / BARRIER_COUNT) * 2 * math.pi
        barrier_x = math.cos(angle) * (GRID_LENGTH - 50)
        barrier_y = math.sin(angle) * (GRID_LENGTH - 50)
        glPushMatrix()
        glTranslatef(barrier_x, barrier_y, wall_height/2)
        angle_deg = math.degrees(angle) + 90
        glRotatef(angle_deg, 0, 0, 1)
        glColor3f(0.7, 0.7, 0.7)
        glPushMatrix()
        glScalef(30, 120, wall_height)
        glutSolidCube(1)
        glPopMatrix()
        glPushMatrix()
        glTranslatef(0, 0, wall_height/2 + 1)
        glColor3f(0.9, 0.3, 0.0)
        glScalef(32, 122, 3)
        glutSolidCube(1)
        glPopMatrix()
        for _ in range(5):
            glPushMatrix()
            spot_x = random.uniform(-10, 10)
            spot_y = random.uniform(-50, 50)
            spot_z = random.uniform(-wall_height/3, wall_height/3)
            spot_size = random.uniform(5, 15)
            glTranslatef(spot_x, spot_y, spot_z)
            glColor3f(0.3, 0.3, 0.3)
            glScalef(spot_size, spot_size, 3)
            glutSolidCube(1)
            glPopMatrix()
        for spike_pos in [-40, -20, 0, 20, 40]:
            glPushMatrix()
            glTranslatef(0, spike_pos, wall_height)
            glColor3f(0.5, 0.0, 0.0)
            glRotatef(90, 1, 0, 0)
            glutSolidCone(5, 20, 8, 8)
            glPopMatrix()
        glPopMatrix()
    for x, y in [(-1,-1), (-1,1), (1,-1), (1,1)]:
        pillar_x = x * (GRID_LENGTH - 30)
        pillar_y = y * (GRID_LENGTH - 30)
        glPushMatrix()
        glTranslatef(pillar_x, pillar_y, wall_height)
        glColor3f(0.3, 0.3, 0.3)
        glutSolidCube(60)
        glPushMatrix()
        glTranslatef(0, 0, 40)
        glColor3f(0.5, 0.0, 0.0)
        glutSolidCylinder(20, 80, 16, 16)
        glTranslatef(0, 0, 80)
        glColor3f(0.7, 0.1, 0.1)
        glutSolidSphere(25, 16, 16)
        glPopMatrix()
        glPopMatrix()
    glEnable(GL_LIGHTING)

def draw_text(x, y, text, font=GLUT_BITMAP_HELVETICA_18):
    glDisable(GL_LIGHTING)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, WINDOW_W, 0, WINDOW_H)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glEnable(GL_LIGHTING)

def spawn_bullet():
    # Bullet always fires in the direction the player is facing (player_angle)
    px, py, pz = game.player_pos
    angle = game.player_angle
    game.bullets.append(Bullet(px, py, pz + 5, angle))

def auto_fire():
    now = time.time()
    if game.cheat_mode and getattr(game, "is_auto_firing", False) and not game.game_over:
        if now - game.last_shot_time > game.auto_fire_delay:
            spawn_bullet()
            game.last_shot_time = now

def update():
    t_now = time.time()
    delta = t_now - game.frame_time
    game.frame_time = t_now
    delta = min(delta, 0.033)
    if any(game.move_dir):
        game.arm_sway += 0.1 * game.arm_sway_dir
        if abs(game.arm_sway) > 1:
            game.arm_sway_dir *= -1
    # Player movement (8-way)
    if any(game.move_dir):
        movement_angle = math.degrees(math.atan2(game.move_dir[0], game.move_dir[1]))
        game.player_move_angle = movement_angle
        step_len = PLAYER_MOVE_BASE * float(TICKS_PER_SEC) * delta * 0.93
        move_x = math.sin(math.radians(movement_angle)) * step_len
        move_y = math.cos(math.radians(movement_angle)) * step_len
        game.player_pos[0] += move_x
        game.player_pos[1] += move_y
    # Clamp to grid
    game.player_pos[0] = max(-GRID_LENGTH+PLAYER_SIZE/2, min(GRID_LENGTH-PLAYER_SIZE/2, game.player_pos[0]))
    game.player_pos[1] = max(-GRID_LENGTH+PLAYER_SIZE/2, min(GRID_LENGTH-PLAYER_SIZE/2, game.player_pos[1]))
    # Bullets update
    i = 0
    while i < len(game.bullets):
        if not game.bullets[i].update():
            del game.bullets[i]
        else:
            i += 1
    # Zombies update
    i = 0
    while i < len(game.enemies):
        if not game.enemies[i].update():
            del game.enemies[i]
            game.last_enemy_kill_time = time.time()
        else:
            i += 1
    # Health pickup update
    if game.health_pickup and not game.health_pickup.update():
        game.health_pickup = None
    # Bullet-zombie collision
    i = 0
    while i < len(game.bullets):
        hit = False
        j = 0
        while j < len(game.enemies):
            dx = game.bullets[i].x - game.enemies[j].x
            dy = game.bullets[i].y - game.enemies[j].y
            dist = math.hypot(dx, dy)
            zombie_radius = game.enemies[j].radius
            if dist < zombie_radius + BULLET_RADIUS:
                was_alpha = game.enemies[j].is_alpha
                del game.enemies[j]
                hit = True
                game.score += 2 if was_alpha else 1
                game.last_enemy_kill_time = time.time()
                if was_alpha:
                    game.alpha_zombie_killed = True
                    game.health_pickup = HealthPickup(game.bullets[i].x, game.bullets[i].y)
                break
            else:
                j += 1
        if hit:
            del game.bullets[i]
        else:
            i += 1
    # Hit effects
    i = 0
    while i < len(game.hit_effects):
        if not game.hit_effects[i].update():
            del game.hit_effects[i]
        else:
            i += 1
    # Game Over conditions
    if not game.cheat_mode:
        if game.health <= 0 or game.missed_shots >= MAX_MISSED_SHOTS:
            game.health = max(0, game.health)
            game.game_over = True
    else:
        game.health = PLAYER_MAX_HEALTH  # Always restore
        game.missed_shots = 0            # Unlimited misses
    # Level up progression
    prev_level = game.level
    game.level = 1 + game.score // LEVEL_UP_EVERY
    if game.level != prev_level:
        game.zombie_speed += 0.015
        if game.level % LIFE_AWARD_EVERY_LEVELS == 0 and game.health < PLAYER_MAX_HEALTH:
            game.health = min(PLAYER_MAX_HEALTH, game.health + 1)
    game.zombie_count = BASE_ZOMBIE_NUM + game.score // ZOMBIE_NUM_STEP_KILLS

def ensure_zombie_count():
    current_time = time.time()
    # Respawn delay after kills
    if game.last_enemy_kill_time > 0 and (current_time - game.last_enemy_kill_time) < ENEMY_RESPAWN_DELAY:
        return
    # Spawn alpha zombie on every 5th level
    if not game.has_alpha_zombie and not game.alpha_zombie_killed:
        if game.level % 5 == 0 and game.level != 0:
            game.enemies.append(Zombie(game.zombie_speed, game.zombie_speed + 0.1, is_alpha=True))
            game.has_alpha_zombie = True
    if game.alpha_zombie_killed:
        game.has_alpha_zombie = False
        game.alpha_zombie_killed = False
    while len(game.enemies) < game.zombie_count:
        # Regular zombies fill remaining count
        game.enemies.append(Zombie(game.zombie_speed, game.zombie_speed + 0.07 + 0.12*random.random()))

def reset_game():
    game.player_pos = [0.0, 0.0, 30.0]
    game.player_angle = 0.0
    game.player_move_angle = 0.0
    game.bullets = []
    game.enemies = []
    game.score = 0
    game.level = 1
    game.health = PLAYER_START_HEALTH
    game.missed_shots = 0
    game.game_over = False
    game.last_enemy_kill_time = 0
    game.hit_effects = []
    game.zombie_count = BASE_ZOMBIE_NUM
    game.zombie_speed = 0.05  # Lower initial zombie speed
    game.frame_time = time.time()
    game.move_dir = [0, 0]
    game.hit_time = 0
    game.health_pickup = None
    game.has_alpha_zombie = False
    game.alpha_zombie_killed = False
    game.rounds_since_alpha = 0
    game.arm_sway = 0
    game.arm_sway_dir = 1
    ensure_zombie_count()

def setupCamera():
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(62, WINDOW_W/WINDOW_H, 0.1, 1800)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    if game.camera_mode == 0: # Third person
        cam_x = game.player_pos[0] - CAMERA_DISTANCE * math.sin(math.radians(game.player_angle))
        cam_y = game.player_pos[1] - CAMERA_DISTANCE * math.cos(math.radians(game.player_angle))
        cam_z = game.player_pos[2] + CAMERA_HEIGHT
        gluLookAt(cam_x, cam_y, cam_z, *game.player_pos, 0, 0, 1)
    elif game.camera_mode == 1: # First person
        cam_x = game.player_pos[0]
        cam_y = game.player_pos[1]
        cam_z = game.player_pos[2] + PLAYER_SIZE/2
        look_x = cam_x + math.sin(math.radians(game.player_angle))
        look_y = cam_y + math.cos(math.radians(game.player_angle))
        look_z = cam_z
        gluLookAt(cam_x, cam_y, cam_z, look_x, look_y, look_z, 0, 0, 1)
    elif game.camera_mode == 2: # Top down
        gluLookAt(0, 0, 530, 0, 0, 0, 0, 1, 0)

def display():
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glClearColor(0.13, 0.01, 0.03, 1.0)
    setupCamera()
    draw_grid()
    draw_boundaries()
    if game.camera_mode != 1:
        draw_player()
    draw_bullets()
    draw_zombies()
    draw_hit_effects()
    if game.health_pickup:
        draw_health_pickup()
    # -- HUD --
    glDisable(GL_LIGHTING)
    if game.cheat_mode:
        glColor3f(0, 1, 0)  # Green in cheat mode
    else:
        glColor3f(1, 0, 0)  # Red in normal
    draw_text(10, 760, "Health: " + "♥ " * game.health + "♡ " * (PLAYER_MAX_HEALTH - game.health))
    draw_text(10, 720, f"Score: {game.score}   Level: {game.level}")
    draw_text(10, 690, f"Bullets missed: {game.missed_shots}/{MAX_MISSED_SHOTS}")
    if game.has_alpha_zombie:
        draw_text(WINDOW_W - 330, 760, "ALPHA ZOMBIE DETECTED!")
        draw_text(WINDOW_W - 330, 730, "Kill for health pickup!")
    if game.cheat_mode:
        draw_text(10, 650, "CHEAT MODE ACTIVE")
    if game.game_over:
        draw_text(340, 400, "GAME OVER -- Press R to Restart")
    glEnable(GL_LIGHTING)
    # --- Update game logic if alive
    if not game.game_over:
        update()
        ensure_zombie_count()
        auto_fire()
    glutSwapBuffers()

def keyboardListener(key, x, y):
    if key == b'w':      game.move_dir[1] = 1
    elif key == b's':    game.move_dir[1] = -1
    elif key == b'a':    game.move_dir[0] = -1
    elif key == b'd':    game.move_dir[0] = 1
    elif key == b'c':    game.cheat_mode = not game.cheat_mode
    elif key == b'v':    game.camera_mode = (game.camera_mode + 1) % 3
    elif key == b'r':
        reset_game()
    elif key == b'q' or key == b'\x1b':
        sys.exit()

def keyboardUpListener(key, x, y):
    if key in [b'w', b's']: game.move_dir[1] = 0
    if key in [b'a', b'd']: game.move_dir[0] = 0

def specialKeyListener(key, x, y):
    pass

def mouseListener(button, state, x, y):
    # Right click: toggle camera
    if button == GLUT_RIGHT_BUTTON and state == GLUT_DOWN:
        game.camera_mode = (game.camera_mode + 1) % 3
    # Left click logic (single shot normally, auto in cheat)
    if button == GLUT_LEFT_BUTTON:
        if state == GLUT_DOWN and not game.game_over:
            if game.cheat_mode:
                # Enable true auto-fire
                game.is_auto_firing = True
            if game.cheat_mode or len(game.bullets) < MAX_BULLETS:
                spawn_bullet()  # Always spawn on click/press
        if state == GLUT_UP and hasattr(game, "is_auto_firing"):
            game.is_auto_firing = False

def mouseMotion(x, y):
    center_x = WINDOW_W // 2
    dx = x - center_x
    game.player_angle = dx * MOUSE_SENS

def main():
    glutInit(sys.argv)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(WINDOW_W, WINDOW_H)
    glutCreateWindow(b"Zombie Blockade: 3D Survival")
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    light_position = [0.0, 0.0, 1.0, 0.0]
    glLightfv(GL_LIGHT0, GL_POSITION, light_position)
    glLightfv(GL_LIGHT0, GL_AMBIENT, [0.18, 0.03, 0.04, 1.0])
    glutDisplayFunc(display)
    glutIdleFunc(display)
    glutKeyboardFunc(keyboardListener)
    glutKeyboardUpFunc(keyboardUpListener)
    glutSpecialFunc(specialKeyListener)
    glutMouseFunc(mouseListener)
    glutPassiveMotionFunc(mouseMotion)
    reset_game()
    glutMainLoop()

if __name__ == '__main__':
    main()
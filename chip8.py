"""
CHIP-8 interpreter written in Python 3.6

http://devernay.free.fr/hacks/chip8/C8TECH10.HTM
"""
# Memory: 4KiB (4096 B)
# Registers: 16 x 1 Byte: V0, V1, ..., VF; VF holds flags. One 16-bit register: I. Two timer registers that are decreased at 60Hz for delay and sound
# Stack: stores return addresses for subroutine calls: space for 16 addresses
# 
# Display: 64x32 monochrome

import sys
import random
import time
import os
import threading

DEBUG = False

def p(s, end="\n"):
    if DEBUG:
        p(s, end=end)

class Display:
    def __init__(self, width=64, height=32):
        self.width = width
        self.height = height
        self.clear()

    def show(self):
        # TODO: draw the actual screen
        os.system('clear')
        for y in range(len(self.screen)):
            for x in range(len(self.screen[y])):
                c = "\u2588" if self.screen[y][x] else " "
                sys.stdout.write(c)
            sys.stdout.write("\n")

    def clear(self):
        self.screen = [[False for _ in range(self.width)] for _ in range(self.height)]
        # self.show()

    def draw(self, start_x, start_y, sprite):
        """
        Draw on the display by XORing the sprite with the current content
        and return True if any pixels where erased during that process
        The screen wraps around on all sides

        sprite is a sequence of bytes as read from memory
        """
        flag = False
        for y in range(len(sprite)):
            for x in range(8):
                if (sprite[y] & (0x80>>x)) > 0:
                    # set flag or keep it 
                    flag |= self.screen[(start_y+y)%self.height][(start_x+x)%self.width]
                    # flip the it in the screen
                    self.screen[(start_y+y)%self.height][(start_x+x)%self.width] ^= True

        # self.show()
        return flag

class CPU:
    def __init__(self, program=None):
        self.timer_lock = threading.Lock()
        self.timer_thread = threading.Thread(target=self._timer_task)
        self.reset()
        self.display = Display()
        if program is not None:
            self.load(program)

    def reset(self):
        # stop the timer
        if self.timer_thread.is_alive():
            self.halt = True
            self.timer_thread.join()
            self.timer_thread = threading.Thread(target=self._timer_task)

        self.halt = False
        self.timer_thread.start()
        # programs are copied into RAM and execution starts at address 0x200
        self.pc = 0x200  # 16 bit
        self.memory = [0 for _ in range(0xFFF)]  # each cell: 8 bit
        self.V = [0 for x in range(0xF+1)]  # each register: 8 bit
        self.I = 0  # 16 bit
        self.delay = 0  # 8 bit
        self.sound = 0  # 8 bit
        self.stack = [0 for _ in range(16)]  # each cell: 16 bit
        self.sp = 0  # 8 bit
        self._store_hex_sprites()
        random.seed(time.time())

    def load(self, program):
        if type(program) in [bytes, list]:
            self.memory[self.pc:self.pc+len(program)] = program

    def _execute(self, opcode):
        p("pc:{0:03X}, V0:{1:02X}, VF:{2:02X}, I:{3:04X}, sp:{4:02X}, stack[0]:{5:03X} ,opcode:{6:04X} ".format(self.pc-2, self.V[0], self.V[0XF], self.I, self.sp, self.stack[0], opcode), end="")
        addr = opcode & 0x0FFF
        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        kk = opcode & 0x00FF

        if opcode == 0x00E0:
            # CLS
            p("CLS")
            self.display.clear()
            self.display.show()

        elif opcode == 0x00EE:
            # RET
            p("RET")
            self.sp -= 1
            self.pc = self.stack[self.sp]

        elif opcode & 0xF000 == 0x1000:
            # JP addr
            p("JP {addr:03X}".format(addr=addr))
            self.pc = addr

        elif opcode & 0xF000 == 0x2000:
            # CALL addr
            p("CALL addr")
            self.stack[self.sp] = self.pc
            self.sp += 1
            self.pc = addr

        elif opcode & 0xF000 == 0x3000:
            # SE Vx, byte
            p("SE Vx, byte")
            if self.V[x] == kk:
                self.pc += 2

        elif opcode & 0xF000 == 0x4000:
            # SNE Vx, byte
            p("SNE Vx, byte")
            if self.V[x] != kk:
                self.pc += 2

        elif opcode & 0xF000 == 0x5000:
            # SE Vx, Vy
            p("SE Vx, Vy")
            if self.V[x] == self.V[y]:
                self.pc += 2

        elif opcode & 0xF000 == 0x6000:
            # LD Vx, byte
            p("LD Vx, byte")
            self.V[x] = kk

        elif opcode & 0xF000 == 0x7000:
            # ADD Vx, byte
            p("ADD Vx, byte")
            self.V[x] += kk
            self.V[x] &= 0xFF

        elif opcode & 0xF00F == 0x8000:
            # LD Vx, Vy
            p("LD Vx, Vy")
            self.V[x] = self.V[y]

        elif opcode & 0xF00F == 0x8001:
            # OR Vx, Vy
            p("OR Vx, Vy")
            self.V[x] |= self.V[y]

        elif opcode & 0xF00F == 0x8002:
            # AND Vx, Vy
            p("AND Vx, Vy")
            self.V[x] &= self.V[y]

        elif opcode & 0xF00F == 0x8003:
            # XOR Vx, Vy
            p("XOR Vx, Vy")
            self.V[x] ^= self.V[y]

        elif opcode & 0xF00F == 0x8004:
            # ADD Vx, Vy
            p("ADD Vx, Vy")
            self.V[x] += self.V[y]
            self.V[0xF] = 1 if self.V[x] > 0xFF else 0
            self.V[x] &= 0xFF

        elif opcode & 0xF00F == 0x8005:
            # SUB Vx, Vy
            p("SUB Vx, Vy")
            self.V[0xF] = 1 if self.V[x] > self.V[y] else 0

            self.V[x] -= self.V[y]
            self.V[x] &= 0xFF

        elif opcode & 0xF00F == 0x8006:
            # SHR Vx {, Vy}
            p("SHR Vx {, Vy}")
            self.V[0xF] = self.V[x] & 0x1
            self.V[x] >>= 1

        elif opcode & 0xF00F == 0x8007:
            # SUBN Vx, Vy
            p("SUBN Vx, Vy")
            self.V[0xF] = 1 if self.V[y] > self.V[x] else 0
            self.V[x] = self.V[y] - self.V[x]

        elif opcode & 0xF00F == 0x800E:
            # SHL Vx {, Vy}
            p("SHL Vx {, Vy}")
            self.V[0xF] = self.V[x] & 0x80
            self.V[x] <<= 1

        elif opcode & 0xF000 == 0x9000:
            # SNE Vx, Vy
            p("SNE Vx, Vy")
            if self.V[x] != self.V[y]:
                self.pc += 2

        elif opcode & 0xF000 == 0xA000:
            # LD I, addr
            p("LD I, addr")
            self.I = addr

        elif opcode & 0xF000 == 0xB000:
            # JP V0, addr
            p("JP V0, addr")
            self.pc = addr + self.V[0]

        elif opcode & 0xF000 == 0xC000:
            # RND Vx, byte
            p("RND Vx, byte")
            self.V[x] = random.randint(0,0xFF) & kk

        elif opcode & 0xF000 == 0xD000:
            # DRW Vx, Vy, nibble
            p("DRW Vx, Vy, nibble")
            n = opcode & 0x000F
            sprite = self.memory[self.I:self.I+n]
            self.display.draw(self.V[x], self.V[y], sprite)
            self.display.show()

        elif opcode & 0xF0FF == 0xE09E:
            # SKP Vx
            p("SKP Vx")
            #TODO: poll the keyboard,
            #      if the key with the value from Vx is currently pressed:
            #          skip the next instruction
            pass

        elif opcode & 0xF0FF == 0xE0A1:
            # SKNP Vx
            p("SKNP Vx")
            #TODO: same but skip if currently not pressed
            pass

        elif opcode & 0xF0FF == 0xF007:
            # LD Vx, DT
            p("LD Vx, DT")
            with self.timer_lock:
                self.V[x] = self.delay

        elif opcode & 0xF0FF == 0xF00A:
            # LD Vx, K
            p("LD Vx, K")
            val = 0
            while True:
                val = int(input(), 16)
                if val <= 0xF:
                    break

            self.V[x] = val

        elif opcode & 0xF0FF == 0xF015:
            # LD DT, Vx
            p("LD DT, Vx")
            with self.timer_lock:
                self.delay = self.V[x]

        elif opcode & 0xF0FF == 0xF018:
            # LD ST, Vx
            p("LD ST, Vx")
            with self.timer_lock:
                self.sound = self.V[x]

        elif opcode & 0xF0FF == 0xF01E:
            # ADD I, Vx
            p("ADD I, Vx")
            self.I += self.V[x]
            self.I &= 0xFFFF

        elif opcode & 0xF0FF == 0xF029:
            # LD F, Vx
            p("LD F, Vx")
            self.I = self.hex_sprite_offset + 5*self.V[x]

        elif opcode & 0xF0FF == 0xF033:
            # LD B, Vx
            p("LD B, Vx")
            self.memory[self.I] = (self.V[x] % 1000) // 100
            self.memory[self.I+1] = (self.V[x] % 100) // 10
            self.memory[self.I+2] = self.V[x] % 10

        elif opcode & 0xF0FF == 0xF055:
            # LD [I], Vx
            p("LD [I], Vx")
            for offset in range(x+1):
                self.memory[self.I+offset] = self.V[offset]

        elif opcode & 0xF0FF == 0xF065:
            # LD Vx, [I]
            p("LD Vx, [I]")
            for offset in range(x+1):
                self.V[offset] = self.memory[self.I+offset]

        else:
            # error! unknown opcode, halt the machine
            self.halt = True


    def run(self):
        while not self.halt:

            # fetch
            opcode = (self.memory[self.pc]<<8) + self.memory[self.pc+1]
            self.pc += 2

            # execute
            self._execute(opcode)

            sound = 0
            with self.timer_lock:
                sound = self.sound

            if sound > 0:
                # TODO: play sound
                pass

    def _store_hex_sprites(self):
        self.hex_sprite_offset = 0
        h = self.hex_sprite_offset
        self.memory[(h+0 ):(h+5 )] = [0xF0, 0x90, 0x90, 0x90, 0xF0]  # 0
        self.memory[(h+5 ):(h+10)] = [0x20, 0x60, 0x20, 0x20, 0x70]  # 1
        self.memory[(h+10):(h+15)] = [0xF0, 0x10, 0xF0, 0x80, 0xF0]  # 2
        self.memory[(h+15):(h+20)] = [0xF0, 0x10, 0xF0, 0x10, 0xF0]  # 3
        self.memory[(h+20):(h+25)] = [0x90, 0x90, 0xF0, 0x10, 0x10]  # 4
        self.memory[(h+25):(h+30)] = [0xF0, 0x80, 0xF0, 0x10, 0xF0]  # 5
        self.memory[(h+30):(h+35)] = [0xF0, 0x80, 0xF0, 0x90, 0xF0]  # 6
        self.memory[(h+35):(h+40)] = [0xF0, 0x10, 0x20, 0x40, 0x40]  # 7
        self.memory[(h+40):(h+45)] = [0xF0, 0x90, 0xF0, 0x90, 0xF0]  # 8
        self.memory[(h+45):(h+50)] = [0xF0, 0x90, 0xF0, 0x10, 0xF0]  # 9
        self.memory[(h+50):(h+55)] = [0xF0, 0x90, 0xF0, 0x90, 0x90]  # A
        self.memory[(h+55):(h+60)] = [0xE0, 0x90, 0xE0, 0x90, 0xE0]  # B
        self.memory[(h+60):(h+65)] = [0xF0, 0x80, 0x80, 0x80, 0xF0]  # C
        self.memory[(h+65):(h+70)] = [0xE0, 0x90, 0x90, 0x90, 0xE0]  # D
        self.memory[(h+70):(h+75)] = [0xF0, 0x80, 0xF0, 0x80, 0xF0]  # E
        self.memory[(h+75):(h+80)] = [0xF0, 0x80, 0xF0, 0x80, 0x80]  # F


    def _timer_task(self):
        tick = 0
        adjust_ticks = 60
        tick_len = 1.0/60.0
        next_adjust = time.time() + adjust_ticks * tick_len
        # no need to lock the halt flag because we only read from it
        while not self.halt:
            tick += 1
            if tick % adjust_ticks == 0:
                # adjust for clock drift every second
                if next_adjust - time.time() > 0:
                    time.sleep(next_adjust - time.time())
                next_adjust += adjust_ticks * tick_len
            else:
                time.sleep(tick_len)

            # decrement timer registers
            with self.timer_lock:
                if self.delay > 0:
                    self.delay -= 1
                if self.sound > 0:
                    self.sound -= 1




def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            program = f.read()
    else:
        program = sys.stdin.buffer.read()

    cpu = CPU(program)
    cpu.run()


if __name__ == "__main__":
    main()

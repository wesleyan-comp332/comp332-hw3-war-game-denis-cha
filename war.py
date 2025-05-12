"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.
"""
Game = namedtuple("Game", ["p1", "p2", "hand1", "hand2", "cards_played", "socket1", "socket2"])

# Stores the clients waiting to get connected to other clients
waiting_clients = []


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock, numbytes):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    data = b''
    while len(data) < numbytes:
        data_chunk = sock.recv(numbytes - len(data))
        if not data_chunk:
            raise EOFError(f"Only recieved {len(data)} bytes out of {numbytes} bytes before reaching EOF")
        data += data_chunk
    return data


def kill_game(game):
    """
    If either client sends a bad message, immediately nuke the game.
    """
    try:
        game.socket1.close()
    except(Exception):
        pass

    try:
        game.socket2.close()
    except(Exception):
        pass

def compare_cards(card1, card2):
    """
    Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    c1 = (card1 - 2 ) % 13
    c2 = (card2 - 2) % 13
    if (c1 > c2):
        return 1
    elif (c1 < c2):
        return -1
    return 0
    
def deal_cards():
    """
    Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    card_deck = list(range(52))

    random.shuffle(card_deck)
    return card_deck[:26], card_deck[26:]
    

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, port))
    except (socket.error, socket.gaierror, socket.timeout, socket.herror):
        return
    s.listen()

    while True:
        new_client, _ = s.accept()

        try:
            initial_msg = int.from_bytes(readexactly(new_client, 1), byteorder='big')
            if initial_msg != Command.WANTGAME:
                raise Exception("Invalid Initial message")
            waiting_clients.append(new_client)
        except:
            new_client.close()

        while len(waiting_clients) >= 2:
            client1 = waiting_clients.pop(0)
            client2 = waiting_clients.pop(0)
            #initiliaze game
            h1, h2 = deal_cards()

            game = Game(
                p1="player_1",
                p2="player_2",
                hand1= h1,
                hand2= h2,
                cards_played=[],
                socket1=client1,
                socket2=client2,
                game_not_over = True
            )

           
            game.socket1.sendall(Command.GAMESTART.to_bytes(1, byteorder ='big') + str(game.hand1).encode())
            game.socket2.sendall(Command.GAMESTART.to_bytes(1, byteorder ='big') + str(game.hand2).encode())
            while game.game_not_over:
                try:
                    msg1 = int.from_bytes(readexactly(game.socket1, 2), byteorder='big')
                    msg2 = int.from_bytes(readexactly(game.socket2, 2), byteorder='big')
                    comm1 = int.from_bytes(msg1[0], byteorder='big')
                    comm2 = int.from_bytes(msg2[0], byteorder='big')
                    card1 = msg1[1]
                    card2 = msg2[1]
                    if comm1 != Command.PLAYCARD or comm2 != Command.PLAYCARD:
                        raise Exception ("Message isn't a PLAYCARD Command")

                    if card1 in game.cards_played or card2 in game.cards_played:
                        raise Exception("Replayed a card")
                    elif card1 not in range(0, 51) or card2 not in range(0, 51):
                        raise Exception(" Card number out of range")
                    else:
                        game.cards_played.append(card1)
                        game.cards_played.append(card2)
                    result = compare_cards(card1, card2)
                    if result == 1:
                        game.socket1.sendall(Command.PLAYRESULT.to_bytes(1, byteorder= 'b') + Result.WIN.to_bytes(1, byteorder='big'))
                        game.socket2.sendall(Command.PLAYRESULT.to_bytes(1, byteorder= 'b') + Result.LOSE.to_bytes(1, byteorder='big'))
                    elif result == -1:
                        game.socket2.sendall(Command.PLAYRESULT.to_bytes(1, byteorder= 'b') + Result.WIN.to_bytes(1, byteorder='big'))
                        game.socket1.sendall(Command.PLAYRESULT.to_bytes(1, byteorder= 'b') + Result.LOSE.to_bytes(1, byteorder='big'))
                    else:
                        game.socket1.sendall(Command.PLAYRESULT.to_bytes(1, byteorder= 'b') + Result.DRAW.to_bytes(1, byteorder='big'))
                        game.socket2.sendall(Command.PLAYRESULT.to_bytes(1, byteorder= 'b') + Result.DRAW.to_bytes(1, byteorder='big'))

                    if len(game.cards_played) >= 52:
                        game = game._replace(game_not_over = False)


                except Exception as e:
                    print(f"Exception during the game: {e}")
                    kill_game(game)
                    game = game._replace(game_not_over = False)

                



    

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])

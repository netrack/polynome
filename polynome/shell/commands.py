import argparse
import enum
import importlib
import pathlib

import polynome.client
import polynome.errors

from polynome import asynclib


class ExitStatus(enum.Enum):
    Success = 0
    Failure = 1


class Formatter(argparse.ArgumentDefaultsHelpFormatter):

    def __init__(self,
                 prog,
                 indent_increment=2,
                 max_help_position=48,
                 width=120):
        super().__init__(prog,
                         indent_increment,
                         max_help_position,
                         width)


class Command:
    """Shell sub-command."""

    __attributes__ = [
        "name",
        "aliases",
        "arguments",
        "help",
        "description",
    ]

    def __init__(self, subparsers):
        # Copy all meta parameters of the command into the __meta__ dictionary,
        # so it can be accessible during the setup of commands.
        attrs = {attr: getattr(self, attr, None)
                 for attr in self.__attributes__}

        self.__meta__ = argparse.Namespace(**attrs)
        self.subcommands = {}

        self.subparser = subparsers.add_parser(
            name=self.__meta__.name,
            help=self.__meta__.help,
            aliases=(self.__meta__.aliases or []),
            description=self.__meta__.description,
            formatter_class=Formatter)

        for args, kwargs in self.__meta__.arguments or []:
            self.subparser.add_argument(*args, **kwargs)

        # At least print the help message for the command.
        self.subparser.set_defaults(func=self.handle)

        # Search for sub-classes that represent sub-commands.
        class_dict = self.__class__.__dict__

        subcommands = filter(lambda o: isinstance(o, type),
                             class_dict.values())

        subcommands = list(subcommands)
        if not subcommands:
            return

        subparsers = self.subparser.add_subparsers(dest=self.__meta__.name)
        for command_class in subcommands:
            command = command_class(subparsers)
            self.subcommands[command_class.__name__] = command

    def handle(self, args: argparse.Namespace) -> ExitStatus:
        self.subparser.print_help()
        return ExitStatus.Success


class Server(Command):
    """Server shell command used to run a server."""

    name = "server"
    aliases = ["s"]
    help = "run server"

    description = "Start serving models."

    arguments = [
        (["-H", "--host"],
         dict(metavar="HOST",
              help="address to listen to",
              default="localhost")),
        (["-p", "--port"],
         dict(metavar="PORT",
              help="port to listen to",
              default="5678")),
        (["--data-root"],
         dict(metavar="PATH",
              help="root directory of persistent state",
              default="/var/lib/polynome")),
        (["--pidfile"],
         dict(metavar="PIDFILE",
              help="path to use for daemon pid file",
              default="/var/run/polynome.pid")),
        (["--strategy"],
         dict(metavar="STRATEGY",
              choices=["mirrored", "multi_worker_mirrored", "no"],
              default="mirrored",
              help="model execution strategy")),
        (["--preload"],
         dict(action="store_true",
              default=False,
              help="preload all models into the memory before start")),
        (["--tls"],
         dict(action="store_true",
              default=False,
              help="use TLS")),
        (["--tlsverify"],
         dict(action="store_true",
              default=False,
              help="use TLS and verify remove")),
        (["--tlscacert"],
         dict(metavar="TLS_CACERT",
              default=pathlib.Path.home().joinpath(".polynome/cacert.pem"),
              help="trust certs signed only by this CA")),
        (["--tlscert"],
         dict(metavar="TLS_CERT",
              default=pathlib.Path.home().joinpath(".polynome/cert.pem"),
              help="path to TLS certificate file")),
        (["--tlskey"],
         dict(metavar="TLS_KEY",
              default=pathlib.Path.home().joinpath(".polynome/key.pem"),
              help="path to TLS key fine"))]

    def handle(self, args: argparse.Namespace) -> ExitStatus:
        try:
            server = importlib.import_module("polynome.server")
            server.Server.start(**args.__dict__)
        except FileNotFoundError as e:
            print(e)
        return ExitStatus.Success


class Push(Command):
    """Shell command to push model to the server."""

    name = "push"
    aliases = ["p"]
    help = "push model"

    description = "Push a model image to the repository."

    arguments = [
        (["-n", "--name"],
         dict(metavar="NAME",
              type=str,
              required=True,
              default=argparse.SUPPRESS,
              help="model name")),
        (["-t", "--tag"],
         dict(metavar="TAG",
              type=str,
              required=True,
              default=argparse.SUPPRESS,
              help="model tag")),
        (["path"],
         dict(metavar="PATH",
              type=str,
              default=argparse.SUPPRESS,
              help="model location"))]

    def handle(self, args: argparse.Namespace) -> ExitStatus:
        print("loading model {0}:{1}".format(args.name, args.tag))
        client = polynome.client.Client(service_url=args.service_url)

        path = pathlib.Path(args.path)
        task = client.push(args.name, args.tag, path)

        try:
            asynclib.run(task)
        except Exception as e:
            print("Failed to push model. {0}".format(e))
            return ExitStatus.Failure
        return ExitStatus.Success


class Remove(Command):
    """Shell command to remove the model from server."""

    name = "remove"
    aliases = ["rm"]
    help = "remove model"

    description = "Remove a model from the repository."

    arguments = [
        (["-n", "--name"],
         dict(metavar="NAME",
              type=str,
              help="model name")),
        (["-q", "--quiet"],
         dict(action="store_true",
              help="do not return error on missing model")),
        (["-t", "--tag"],
         dict(metavar="TAG",
              type=str,
              help="model tag"))]

    def handle(self, args: argparse.Namespace) -> ExitStatus:
        client = polynome.client.Client(service_url=args.service_url)
        task = client.remove(args.name, args.tag)

        try:
            asynclib.run(task)
        except polynome.errors.NotFoundError as e:
            if not args.quiet:
                print("{0}.".format(e))
                return ExitStatus.Failure
        except Exception as e:
            print("Failed to remove model. {0}.".format(e))
            return ExitStatus.Failure
        return ExitStatus.Success


class List(Command):
    """Shell command to list models from the server."""

    name = "list"
    aliases = ["ls"]
    help = "list models"

    description = "List available models."

    arguments = []

    def handle(self, args: argparse.Namespace) -> ExitStatus:
        client = polynome.client.Client(service_url=args.service_url)
        task = client.list()

        try:
            for model in asynclib.run(task):
                print("{name}:{tag}".format(**model))
        except Exception as e:
            print("Failed to list models. {0}.".format(e))
            return ExitStatus.Failure
        return ExitStatus.Success

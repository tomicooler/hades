import logging
import os
import time
from os import path
from typing import List, Tuple

import click

from core.config import Config
from hadoop.action import RoleAction
from hadoop.app.example import Application
from hadoop.cluster_type import ClusterType
from core.context import HadesContext
from core.error import HadesException, ConfigSetupException, CliArgException
from core.handler import MainCommandHandler
from hadoop.xml_config import HadoopConfigFile
from hadoop_dir.module import HadoopModules

logger = logging.getLogger(__name__)


@click.group()
@click.option('-c', '--config', default='config.json', help='path to config file')
@click.option('-d', '--debug', is_flag=True, help='turn on DEBUG level logging')
@click.pass_context
def cli(ctx, config: str, debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=level)
    sh_log = logging.getLogger("sh")
    sh_log.setLevel(logging.CRITICAL)
    ctx.ensure_object(dict)

    logger.info("Invoked command {}".format(ctx.invoked_subcommand))

    if ctx.invoked_subcommand == "init":
        ctx.obj['handler'] = MainCommandHandler(None)
        ctx.obj['config_path'] = config
        return

    if not path.exists(config):
        raise ConfigSetupException("Config file does not exist. Create config with 'init' subcommand.")

    with open(config) as file:
        json_str = file.read()
        config = Config.from_json(json_str)
        context = HadesContext(config=config)

    ctx.obj['handler'] = MainCommandHandler(context)


@cli.command()
@click.pass_context
@click.option('-c', '--changed', is_flag=True, help='compiles only the changed modules')
@click.option('-d', '--deploy', is_flag=True, help='deploy the changed modules to cluster')
@click.option('-n', '--no-copy', default=False, is_flag=True, help='do not copy the compiled modules jar to hadoop jar path')
@click.option('-m', '--module', multiple=True, help='adds a module to the aggregated compilation')
@click.option('-s', '--single', type=click.Choice([m.name for m in HadoopModules]), help='only compiles a single module')
def compile(ctx, changed: bool, deploy: bool, module: List[str], no_copy: bool, single: str):
    """
    Compiles hadoop modules
    """
    handler: MainCommandHandler = ctx.obj['handler']
    all_modules = []
    single_module = HadoopModules[single] if single else None
    if module:
        all_modules.extend(handler.ctx.config.default_modules)
        all_modules.extend(module)

    handler.compile(changed, deploy, modules=all_modules, no_copy=no_copy, single=single_module)


@cli.command()
@click.pass_context
@click.option('-c', '--cluster-type', type=click.Choice([n.value for n in ClusterType], case_sensitive=False), help='compiles only the changed modules')
@click.option('-h', '--host', help='set the Cloudera Manager host')
@click.option('-u', '--username', default="admin", help='sets the username credential when communicating with Cloudera Manager')
@click.option('-p', '--password', default="admin", help='sets the password credential when communicating with Cloudera Manager')
@click.option('-d', '--hadock-path', help='sets the Hadock repository path')
def init(ctx, cluster_type: ClusterType or None, host: str or None, username: str or None, password: str or None, hadock_path: str or None):
    """
    Initializes config file
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.init(ctx.obj['config_path'], ClusterType(cluster_type), {
        'host': host,
        'username': username,
        'password': password,
        'hadock_path': hadock_path
    })


@cli.command()
@click.pass_context
@click.argument('selector')
@click.option('-f', '--follow', is_flag=True, help='whether to follow the logs file instead of just reading it')
@click.option('-t', '--tail', default=None, help='only read the last N lines')
@click.option('-g', '--grep', default=None, help='only read the lines that have this substring')
def log(ctx, selector: str, follow: bool, tail: int or None, grep: str or None):
    """
    Read the logs of Hadoop roles
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.log(selector, follow, tail, grep)


@cli.command()
@click.argument("selector", default="")
@click.option('-f', '--file', multiple=True, help='path of local file to distribute to role hosts')
@click.pass_context
def distribute(ctx, selector: str, file: Tuple[str]):
    """
    Distributes files to selected roles
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.distribute(selector, file)


@cli.command()
@click.pass_context
def status(ctx):
    """
    Prints the status of cluster
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.print_status()
    handler.print_cluster_metrics()


@cli.command()
@click.pass_context
@click.argument('app', type=click.Choice([n.name for n in Application], case_sensitive=False))
@click.option('-c', '--cmd', help='defines the command to run')
@click.option('-q', '--queue', help='defines the queue to which the application will be submitted')
def run_app(ctx, app: str, cmd: str = None, queue: str = None):
    """
    Runs an application on the defined cluster
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.run_app(app, cmd, queue)


@cli.command()
@click.pass_context
@click.argument('script')
def run_script(ctx, script: str):
    """
    Runs the selected Hades script file in script/ directory
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.run_script(script)


@cli.command()
@click.pass_context
@click.argument('selector', default="")
@click.option('-f', '--file', type=click.Choice([n.value for n in HadoopConfigFile]), required=True, help='which config file to update')
@click.option('-p', '--property', multiple=True, help='property name')
@click.option('-v', '--value', multiple=True, help='property value')
@click.option('-s', '--source', help='update the config from a local file')
@click.option('-n', '--no-backup', is_flag=True, help='do not create a backup file before making any change to the config file')
def update_config(ctx, selector: str, file: str, property: Tuple[str], value: Tuple[str], no_backup: bool = False,
                  source: str = None):
    """
    Update properties on a config file for selected roles
    """
    if len(property) != len(value):
        raise CliArgException("All property must map to a value. Properties: {} Values: {}".format(len(property), len(value)))

    handler: MainCommandHandler = ctx.obj['handler']
    file = HadoopConfigFile(file)
    handler.update_config(selector, file, list(property), list(value), no_backup, source)


@cli.command()
@click.pass_context
@click.argument('selector', default="")
def restart_role(ctx, selector: str):
    """
    Restart a role
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.role_action(selector, RoleAction.RESTART)


@cli.group()
@click.pass_context
def yarn(ctx):
    """
    Yarn specific commands
    """
    pass


@yarn.command()
@click.pass_context
def queue(ctx):
    """
    Prints Yarn queues
    """
    handler: MainCommandHandler = ctx.obj['handler']
    handler.print_queues()


if __name__ == "__main__":
    logger.info("Started application")
    before = time.time()
    try:
        cli()
        after = time.time()
        logger.info("Executed successfully after {}s".format(int(after - before)))
    except HadesException as e:
        logger.error(str(e))

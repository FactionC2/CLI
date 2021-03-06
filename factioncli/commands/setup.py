import logging
from time import sleep

from cliff.command import Command

from factioncli.processing.cli.printing import print_output, error_out
from factioncli.processing.config import generate_config_file, get_config
from factioncli.processing.faction.database import update_database, create_database_migration
from factioncli.processing.docker.compose import write_build_compose_file, write_hub_compose_file, write_dev_compose_file
from factioncli.processing.faction.control import build_faction
from factioncli.processing.faction.repo import download_github_repo, clone_github_repo
from factioncli.processing.setup.networking import get_ip_addresses
from factioncli.processing.docker.container import get_container, get_container_status, restart_container


class Setup(Command):
    "Handles setting up Faction"

    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = super(Setup, self).get_parser(prog_name)
        parser.add_argument('--admin-username',
                            help="Username for the default admin",
                            default="admin")
        parser.add_argument('--admin-password',
                            help="Password for the default admin. If not specified, a random password will be generated",
                            default=None)
        parser.add_argument('--api-upload-dir',
                            help="Directory on the API container where uploads are stored. Changing this hasn't been tested and will probably break stuff.",
                            default="/opt/faction/uploads")
        parser.add_argument('--build-for-dev-environment',
                            help="Only build the DB and Message Queue.",
                            action="store_true")
        parser.add_argument('--build-from-source',
                            help="Build Faction from source instead of pulling images from Docker Hub",
                            action="store_true")
        parser.add_argument('--release',
                            help="Whether to use stable or development releases",
                            choices=["stable", "development"],
                            default="stable")
        parser.add_argument('--components',
                            help="Names of the components that make up Faction",
                            default=["Core", "Build-Service-Dotnet", "Console", "API"])
        parser.add_argument('--console-port',
                            help="Port that the console will listen on",
                            default=443)
        parser.add_argument('--container-names',
                            help="Names of the containers that make up Faction",
                            default=["faction_core_1","faction_api_1","faction_console_1","faction_build-dotnet_1","faction_db_1","faction_mq_1"])
        parser.add_argument('--docker-network-name',
                            help="Name of the network used in Docker for Faction Containers.",
                            default="faction-network")
        parser.add_argument('--external-address',
                            help="URL for Faction. If not specified, the public ip address of this host will be used in the format of 'https://<ip_address>'",
                            default=None)
        parser.add_argument('--faction-path',
                            help="Faction install path. Changing this hasn't been tested. It will probably break stuff.",
                            default="/opt/faction")
        parser.add_argument('--flask-secret',
                            help="Secret used by API for various things. Default is to generate a random secret.",
                            default=None)
        parser.add_argument('--github-pat',
                            help="Github Personal Access Token. Used to download stuff from private repos",
                            default=None)
        parser.add_argument('--rabbit-host',
                            help="Hostname/IP for RabbitMQ",
                            default="mq")
        parser.add_argument('--rabbit-username',
                            help="Username for RabbitMQ",
                            default="guest")
        parser.add_argument('--rabbit-password',
                            help="Password for RabbitMQ. If not specified, a random password will be generated",
                            default=None)
        parser.add_argument('--system-username',
                            help="Name for the account that Faction does some stuff with. Really just for display purposes, but changing this might break something.",
                            default="system")
        parser.add_argument('--system-password',
                            help="Password for the system account. This is never used, so the default is a long random password.",
                            default=None)
        parser.add_argument('--postgres-host',
                            help="Hostname/IP for Postgres",
                            default="db")
        parser.add_argument('--postgres-database',
                            help="Database for Postgres",
                            default="faction")
        parser.add_argument('--postgres-username',
                            help="Username for Postgres",
                            default="postgres")
        parser.add_argument('--postgres-password',
                            help="Password for Postgres. If not specified, a random password will be generated",
                            default=None)
        parser.add_argument('--log-file-size',
                            help="Size to make log files before being archived.",
                            default="250m")
        parser.add_argument('--log-file-number',
                            help="Number of log files to archive before rolling over.",
                            default="5")
        return parser

    def take_action(self, parsed_args):
        print_output("Setup started..")

        if parsed_args.external_address:
            if not (parsed_args.external_address.startswith("http://") or parsed_args.external_address.startswith("https://")):
                error_out("Setup failed. --external-address argument must begin with http:// or https://")
        else:
            ip_options = get_ip_addresses()
            while True:
                print_output("Available NICs : IP Addresses")
                for key, value in ip_options.items():
                    print(key, " : ", value)
                selection = input("Please select a NIC that corresponds to the ip address you wish to use: ")
                if selection in ip_options:
                    break
            parsed_args.external_address = "https://" + ip_options[selection]

        generate_config_file(admin_username=parsed_args.admin_username,
                             admin_password=parsed_args.admin_password,
                             api_upload_dir=parsed_args.api_upload_dir,
                             build=parsed_args.build_from_source,
                             console_port=parsed_args.console_port,
                             containers=parsed_args.container_names,
                             docker_network_name=parsed_args.docker_network_name,
                             external_address=parsed_args.external_address,
                             faction_path=parsed_args.faction_path,
                             flask_secret=parsed_args.flask_secret,
                             postgres_host=parsed_args.postgres_host,
                             postgres_database=parsed_args.postgres_database,
                             postgres_username=parsed_args.postgres_username,
                             postgres_password=parsed_args.postgres_password,
                             rabbit_host=parsed_args.rabbit_host,
                             rabbit_username=parsed_args.rabbit_username,
                             rabbit_password=parsed_args.rabbit_password,
                             system_username=parsed_args.system_username,
                             system_password=parsed_args.system_password,
                             log_file_size=parsed_args.log_file_size,
                             log_file_number=parsed_args.log_file_number)

        docker_tag = "latest"
        github_repo = "master"

        if parsed_args.release == "development":
            docker_tag = "dev"
            github_repo = "development"

        if parsed_args.build_from_source:
            for component in parsed_args.components:
                download_github_repo("FactionC2/{0}".format(component),
                                     "{0}/source/{1}".format(parsed_args.faction_path, component),
                                     component, parsed_args.github_pat)
            write_build_compose_file()
        elif parsed_args.build_for_dev_environment:
            write_dev_compose_file()
        else:
            write_hub_compose_file(docker_tag)

        clone_github_repo(github_repo, "FactionC2/Modules-Dotnet", "{0}/modules/dotnet".format(parsed_args.faction_path))
        clone_github_repo(github_repo, "maraudershell/Marauder", "{0}/agents/Marauder".format(parsed_args.faction_path))

        build_faction()

        if parsed_args.build_for_dev_environment:
            print_output("Pausing setup, you need to do stuff.")
            print("Add the following to your hosts file: ")
            print("127.0.0.1 api")
            print("127.0.0.1 db")
            print("127.0.0.1 mq\n")
            print("Run the following commands from the Faction Core directory: ")
            print("1.  dotnet ef migration add 'Initial' (You only have to do this once, unless you change the db schema)")
            print("2.  dotnet ef database update\n")
            input("Press enter to continue setup..")
        else:
            print_output("Waiting 30 seconds for Core to come up..")
            core_down = True
            sleep(30)
            while core_down:
                status = get_container_status('faction_core_1')
                self.log.debug("Got status: {0}".format(status))
                if status:
                    if status.status.lower() == 'running':
                        print_output("Core is up, continuing..")
                        core_down = False
                else:
                    print_output("Core is not up yet. Waiting 15 more seconds..")
                    sleep(15)

            create_database_migration("Initial")
            update_database()

        # Now that the environment is up, we can import common lib
        from factionpy.processing.user import get_user_id
        from factionpy.processing.api_key import new_api_key
        from factioncli.processing.setup.transport import create_direct_transport
        from factioncli.processing.setup.user_role import create_faction_roles
        from factioncli.processing.setup.user import create_admin_user, create_system_user

        create_faction_roles()
        create_system_user()
        create_admin_user()

        print_output("Creating API Key for Direct Transport")
        system_id = get_user_id('system')
        api_key = new_api_key(api_key_type="Transport", user_id=system_id, owner_id=system_id)
        create_direct_transport(api_key=api_key)

        if parsed_args.build_for_dev_environment is None or parsed_args.build_for_dev_environment is False:
            print_output("Restarting Core for database changes..")
            core = get_container("faction_core_1")
            restart_container(core)
        config = get_config()
        print_output("Setup complete! Happy hacking!!\n\nURL: {0}\nUsername: {1}\nPassword: {2}".format(config["EXTERNAL_ADDRESS"], config["ADMIN_USERNAME"], config["ADMIN_PASSWORD"]))


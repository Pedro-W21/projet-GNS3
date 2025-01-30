from GNS3 import Connector
from autonomous_system import AS
from ipv6 import SubNetwork
from writer import LINKS_STANDARD, NOM_PROCESSUS_IGP_PAR_DEFAUT, STANDARD_LOOPBACK_INTERFACE
from ipaddress import IPv6Address


class Router:
    def __init__(self, hostname: str, links, AS_number: int, position=None):
        self.hostname = hostname
        self.links = links
        self.AS_number = AS_number
        self.passive_interfaces = set()
        self.loopback_interfaces = set()
        self.counter_loopback_interfaces = 0
        self.router_id = None
        self.subnetworks_per_link = {}
        self.loopback_subnetworks_per_link = {}
        self.ip_per_link = {}
        self.loopback_ip_per_link = {}
        self.interface_per_link = {}
        self.loopback_interface_per_link = {}
        self.config_str_per_link = {}
        self.loopback_config_str_per_link = {}
        self.voisins_ebgp = {}
        self.voisins_ibgp = set()
        self.available_interfaces = [LINKS_STANDARD[i] for i in range(len(LINKS_STANDARD))]
        self.config_bgp = "!"
        self.position = position if position else {"x": 0, "y": 0}
        self.loopback_address = IPv6Address("0::")
        self.internal_routing_loopback_config = ""
        self.route_maps = {}
        self.used_route_maps = set()


    def __str__(self):
        return f"hostname:{self.hostname}\n links:{self.links}\n as_number:{self.AS_number}"

    def cleanup_used_interfaces(self, autonomous_systems: dict[int, AS], all_routers: dict[str, "Router"],
                                connector: Connector):
        """
        Enlève les interfaces déjà utilisées de self.available_interfaces

        entrées : self (méthode), dictionnaire numéro_d'AS:AS, dictionnaire nom_des_routeurs:Router et Connector au projet GNS3 local
        sorties : changement de self.available_interfaces
        """
        for link in self.links:
            if link.get("interface", False):
                interface_to_remove = link["interface"]
                if interface_to_remove in self.available_interfaces:
                    self.available_interfaces.remove(interface_to_remove)
                    self.interface_per_link[link["hostname"]] = interface_to_remove
            else:
                try:
                    interface_to_remove = connector.get_used_interface_for_link(self.hostname, link["hostname"])
                    if LINKS_STANDARD[interface_to_remove] in self.available_interfaces:
                        self.available_interfaces.remove(LINKS_STANDARD[interface_to_remove])
                        self.interface_per_link[link["hostname"]] = LINKS_STANDARD[interface_to_remove]
                except KeyError as e:
                    print(f"Warning: {e}. Skipping this link.")
                except Exception as e:
                    print(f"Unexpected error during interface cleanup: {self.hostname}->{link['hostname']}: {e}")

    def create_router_if_missing(self, connector: Connector):
        """
        Crée le routeur correspondant dans le projet GNS3 donné si il n'existe pas

        input : Connector au projet GNS3 local
        sorties : changement du projet GNS3
        """
        try:
            connector.get_node(self.hostname)
        except Exception:
            print(f"Node {self.hostname} missing ! Creating node...")
            connector.create_node(self.hostname, "c7200")

    def create_missing_links(self, autonomous_systems: dict[int, AS], all_routers: dict[str, "Router"],
                             connector: Connector):
        """
        Enlève les interfaces déjà utilisées de self.available_interfaces

        entrées :self (méthode), dictionnaire numéro_d'AS:AS, dictionnaire nom_des_routeurs:Router et Connector au projet GNS3 local
        sorties : changement de self.available_interfaces
        """
        for link in self.links:
            if link.get("interface", False):
                interface_1_to_use = link["interface"]
                other_link = None
                for other in all_routers[link["hostname"]].links:
                    if other["hostname"] == self.hostname:
                        other_link = other
                        break
                if other_link != None:
                    if other_link.get("interface", False):
                        interface_2_to_use = other_link["interface"]
                    else:
                        interface_2_to_use = all_routers[link["hostname"]].interface_per_link[self.hostname]
                    print(f"1 : {self.hostname} {link["hostname"]}")
                    connector.create_link_if_it_doesnt_exist(self.hostname, link["hostname"],
                                                             LINKS_STANDARD.index(interface_1_to_use),
                                                             LINKS_STANDARD.index(interface_2_to_use))
                else:
                    raise KeyError("Le routeur cible n'a pas de lien dans l'autre sens")
            else:
                interface_1_to_use = self.interface_per_link[link["hostname"]]
                other_link = None
                for other in all_routers[link["hostname"]].links:
                    if other["hostname"] == self.hostname:
                        other_link = other
                        break
                if other_link != None:
                    if other_link.get("interface", False):
                        interface_2_to_use = other_link["interface"]
                    else:
                        interface_2_to_use = all_routers[link["hostname"]].interface_per_link[self.hostname]
                    print(f"1 : {self.hostname} {link["hostname"]}")
                    connector.create_link_if_it_doesnt_exist(self.hostname, link["hostname"],
                                                             LINKS_STANDARD.index(interface_1_to_use),
                                                             LINKS_STANDARD.index(interface_2_to_use))
                else:
                    raise KeyError("Le routeur cible n'a pas de lien dans l'autre sens")

    def set_interface_configuration_data(self, autonomous_systems: dict[int, AS], all_routers: dict[str, "Router"],
                                         mode: str):
        """
        Génère les string de configuration par lien pour le routeur self

        entrées : self (méthode), dictionnaire numéro_d'AS:AS, dictionnaire nom_des_routeurs:Router
        sorties : changement de plusieurs attributs de l'objet, mais surtout de config_str_per_link qui est rempli des string de configuration valides
        """
        my_as = autonomous_systems[self.AS_number]

        for link in self.links:
            if not self.interface_per_link.get(link["hostname"], False):
                interface_for_link = self.available_interfaces.pop(0)
            else:
                interface_for_link = "FastEthernet2019857/0"

            self.interface_per_link[link["hostname"]] = self.interface_per_link.get(link["hostname"],
                                                                                    interface_for_link)
            if not self.subnetworks_per_link.get(link["hostname"], False):
                if link["hostname"] in my_as.hashset_routers:
                    self.subnetworks_per_link[link["hostname"]] = my_as.ipv6_prefix.next_subnetwork_with_n_routers(2)
                    all_routers[link["hostname"]].subnetworks_per_link[self.hostname] = self.subnetworks_per_link[
                        link["hostname"]]
                else:
                    self.passive_interfaces.add(self.interface_per_link[link["hostname"]])
                    #print(link["hostname"], all_routers[link["hostname"]].AS_number)
                    picked_transport_interface = SubNetwork(
                        my_as.connected_AS_dict[all_routers[link["hostname"]].AS_number][1][self.hostname], 2)
                    self.subnetworks_per_link[link["hostname"]] = picked_transport_interface
                    all_routers[link["hostname"]].subnetworks_per_link[self.hostname] = picked_transport_interface
            elif link["hostname"] not in my_as.hashset_routers:
                self.passive_interfaces.add(self.interface_per_link[link["hostname"]])
            ip_address = self.subnetworks_per_link[link["hostname"]].get_ip_address_with_router_id(
                self.subnetworks_per_link[link["hostname"]].get_next_router_id())
            self.ip_per_link[link["hostname"]] = ip_address
            # print(self.interface_per_link.get(link["hostname"],interface))
            if mode == "cfg":
                extra_config = "\n!\n"
                if my_as.internal_routing == "OSPF":
                    if not link.get("ospf_cost", False):
                        extra_config = f"ipv6 ospf {NOM_PROCESSUS_IGP_PAR_DEFAUT} area 0\n!\n"
                    else:
                        extra_config = f"ipv6 ospf {NOM_PROCESSUS_IGP_PAR_DEFAUT} area 0\n ipv6 ospf cost {link["ospf_cost"]}\n!\n"
                elif my_as.internal_routing == "RIP":
                    extra_config = f"ipv6 rip {NOM_PROCESSUS_IGP_PAR_DEFAUT} enable\n!\n"
                self.config_str_per_link[link[
                    "hostname"]] = f"interface {self.interface_per_link[link["hostname"]]}\n no ip address\n negotiation auto\n ipv6 address {str(ip_address)}/{self.subnetworks_per_link[link["hostname"]].start_of_free_spots * 16}\n ipv6 enable\n {extra_config}"
            elif mode == "telnet":
                # todo : send commands
                extra_config = ""
                if my_as.internal_routing == "OSPF":
                    if not link.get("ospf_cost", False):
                        extra_config = f"ipv6 ospf {NOM_PROCESSUS_IGP_PAR_DEFAUT} area 0\n"
                    else:
                        extra_config = f"ipv6 ospf {NOM_PROCESSUS_IGP_PAR_DEFAUT} area 0\n ipv6 ospf cost {link["ospf_cost"]}\n"
                elif my_as.internal_routing == "RIP":
                    extra_config = f"ipv6 rip {NOM_PROCESSUS_IGP_PAR_DEFAUT} enable\n"
                self.config_str_per_link[link[
                    "hostname"]] = f"interface {self.interface_per_link[link["hostname"]]}\n no shutdown\n no ip address\nipv6 address {str(ip_address)}/{self.subnetworks_per_link[link["hostname"]].start_of_free_spots * 16}\n ipv6 enable\n{extra_config}\n exit\n"
        # print(f"LEN DE FOU : {self.ip_per_link}")

    def set_loopback_configuration_data(self, autonomous_systems: dict[int, AS], all_routers: dict[str, "Router"],
                                        mode: str):
        """
        génère la configuration de loopback unique au routeur ou les commandes de l'interface de loopback du routeur en fonction du mode

        entrées: self (méthode), dictionnaire numéro_d'AS:AS, dictionnaire nom_des_routeurs:Router et mode un str valant "cfg" ou "telnet"
        sorties : modifie self.router_id, self.loopback_address
        
        """
        my_as = autonomous_systems[self.AS_number]
        router_id = my_as.global_router_counter.get_next_router_id()
        self.router_id = router_id
        self.loopback_address = my_as.loopback_prefix.get_ip_address_with_router_id(router_id)
        if my_as.internal_routing == "OSPF":
            if mode == "cfg":
                self.internal_routing_loopback_config = f"ipv6 ospf {NOM_PROCESSUS_IGP_PAR_DEFAUT} area 0\n!\n"
            elif mode == "telnet":
                # todo : telnet command
                self.internal_routing_loopback_config = f"interface {STANDARD_LOOPBACK_INTERFACE}\nno ip address\nipv6 enable\nipv6 address {self.loopback_address}/128\nipv6 ospf {NOM_PROCESSUS_IGP_PAR_DEFAUT} area 0\n"
        elif my_as.internal_routing == "RIP":
            if mode == "cfg":
                self.internal_routing_loopback_config = f"ipv6 rip {NOM_PROCESSUS_IGP_PAR_DEFAUT} enable\n!\n"
            elif mode == "telnet":
                # todo : telnet command
                self.internal_routing_loopback_config = f"interface {STANDARD_LOOPBACK_INTERFACE}\nno ip address\nipv6 enable\nipv6 address {self.loopback_address}/128\nipv6 rip {NOM_PROCESSUS_IGP_PAR_DEFAUT} enable\n"

    def set_bgp_config_data(self, autonomous_systems: dict[int, AS], all_routers: dict[str, "Router"], mode: str):
        """
        Génère le string de configuration bgp du router self

        entrées : self (méthode), dictionnaire numéro_d'AS:AS, dictionnaire nom_des_routeurs:Router
        sorties : changement de plusieurs attributs de l'objet, mais surtout de config_bgp qui contient le string de configuration à la fin de l'exécution de la fonction
        """
        my_as = autonomous_systems[self.AS_number]

        self.voisins_ibgp = my_as.hashset_routers.difference({self.hostname})
        for link in self.links:
            if all_routers[link["hostname"]].AS_number != self.AS_number:
                self.voisins_ebgp[link["hostname"]] = all_routers[link["hostname"]].AS_number
        if mode == "telnet":
            # todo : telnet commands
            self.config_bgp = f"router bgp {self.AS_number}\nbgp router-id {self.router_id}.{self.router_id}.{self.router_id}.{self.router_id}\n"
            config_address_family = ""
            config_neighbors_ibgp = "address-family ipv6 unicast\n"
            for voisin_ibgp in self.voisins_ibgp:
                remote_ip = all_routers[voisin_ibgp].loopback_address
                config_neighbors_ibgp += f"neighbor {remote_ip} remote-as {self.AS_number}\nneighbor {remote_ip} update-source {STANDARD_LOOPBACK_INTERFACE}\n"
                config_address_family += f"neighbor {remote_ip} activate\nneighbor {remote_ip} send-community\n"
            config_neighbors_ebgp = ""
            for voisin_ebgp in self.voisins_ebgp:
                remote_ip = all_routers[voisin_ebgp].ip_per_link[self.hostname]
                remote_as = all_routers[voisin_ebgp].AS_number
                config_neighbors_ebgp += f"neighbor {remote_ip} remote-as {all_routers[voisin_ebgp].AS_number}\n"  # neighbor {remote_ip} update-source {STANDARD_LOOPBACK_INTERFACE}\n neighbor {remote_ip} ebgp-multihop 2\n"
                config_address_family += f"neighbor {remote_ip} activate\nneighbor {remote_ip} send-community\nneighbor {remote_ip} route-map {my_as.community_data[remote_as]["route_map_in_bgp_name"]} in\n"
                if my_as.connected_AS_dict[remote_as][0] != "client":
                    config_address_family += f"neighbor {remote_ip} route-map General-OUT out\n"
                self.used_route_maps.add(remote_as)
            config_address_family += f"network {self.loopback_address}/128\n"
            config_address_family += f"exit\nexit\n"
            self.config_bgp += config_neighbors_ibgp
            self.config_bgp += config_neighbors_ebgp
            self.config_bgp += config_address_family
        elif mode == "cfg":
            config_address_family = ""
            config_neighbors_ibgp = ""
            for voisin_ibgp in self.voisins_ibgp:
                remote_ip = all_routers[voisin_ibgp].loopback_address
                config_neighbors_ibgp += f"  neighbor {remote_ip} remote-as {self.AS_number}\n  neighbor {remote_ip} update-source {STANDARD_LOOPBACK_INTERFACE}\n"
                config_address_family += f"  neighbor {remote_ip} activate\n  neighbor {remote_ip} send-community\n"
            config_neighbors_ebgp = ""
            for voisin_ebgp in self.voisins_ebgp:
                remote_ip = all_routers[voisin_ebgp].ip_per_link[self.hostname]
                remote_as = all_routers[voisin_ebgp].AS_number
                config_neighbors_ebgp += f"  neighbor {remote_ip} remote-as {all_routers[voisin_ebgp].AS_number}\n"  # neighbor {remote_ip} update-source {STANDARD_LOOPBACK_INTERFACE}\n neighbor {remote_ip} ebgp-multihop 2\n"
                config_address_family += f"  neighbor {remote_ip} activate\n  neighbor {remote_ip} send-community\n  neighbor {remote_ip} route-map {my_as.community_data[remote_as]["route_map_in_bgp_name"]} in\n"
                if my_as.connected_AS_dict[remote_as][0] != "client":
                    config_address_family += f"  neighbor {remote_ip} route-map General-OUT out\n"
                self.used_route_maps.add(remote_as)
            config_address_family += f"  network {self.loopback_address}/128\n"
            self.config_bgp = f"""
router bgp {self.AS_number}
 bgp router-id {self.router_id}.{self.router_id}.{self.router_id}.{self.router_id}
 bgp log-neighbor-changes
 no bgp default ipv4-unicast
{config_neighbors_ibgp}{config_neighbors_ebgp}
 !
 address-family ipv4
 exit-address-family
 !
 address-family ipv6
{config_address_family}
 exit-address-family
!
"""

    def update_router_position(self, connector):
        try:
            connector.update_node_position(self.hostname, self.position["x"], self.position["y"])
        except Exception as e:
            print(f"Error updating position for {self.hostname}: {e}")

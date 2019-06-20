import urllib.request
import json
import logging
from urllib.error import URLError, HTTPError
from redis_proxy import RedisProxy
from graphutils import GraphUtils
from redisgraph import Graph, Node
from requests import Session

logger = logging.getLogger(__file__)


class GraphOperations(Session):

    def __init__(self, entrypoint_url, redis_connection):
        self.entrypoint_url = entrypoint_url
        self.redis_connection = redis_connection
        self.connection = redis_connection.get_connection()
        self.vocabulary = 'vocab'
        self.graph_utils = GraphUtils(redis_connection)
        self.redis_graph = Graph("apidoc", redis_connection)
        super().__init__()

    def get_processing(self, url: str, resource: dict) -> None:
        """Synchronize Redis upon new GET operations
        :param url: Resource URL to be updated in Redis.
        :param resource: Resource object fetched from server.
        :return: None.
        """
        # Receiving updated object from the Server
        json_response = super().get(url).json()

        url = url.rstrip('/').replace(self.entrypoint_url, "EntryPoint")
        # Updating Redis
        # First case - When processing a GET for a resource
        try:
            entrypoint, resource_endpoint, resource_id = url.split('/')

            # Building the the collection id, i.e. vocab:Entrypoint/Collection
            redis_collection_id = self.vocabulary + \
                ":" + entrypoint + \
                "/" + resource_endpoint

            collection_members = self.graph_utils.read(
                match="collection",
                where="id='{}'".format(redis_collection_id),
                ret="members")

            # Accessing the members with redis-set response structure
            collection_members = eval(collection_members[0][1][0].decode())
            collection_members.append({'@id': resource['@id'],
                                       '@type': resource['@type']})

            # Updating the collection properties with the nem member
            self.graph_utils.update(
                match="collection",
                where="id='{}'".format(redis_collection_id),
                set="members = \"{}\"".format(str(collection_members)))

            # Creating node for new collection member and commiting to Redis
            self.graph_utils.add_node("objects" + resource['@type'],
                                      resource['@type'] + resource_id,
                                      resource)
            self.graph_utils.commit()

            # Creating relation between collection node and member
            self.graph_utils.create_relation(label_source="collection",
                                             where_source="type : \'" +
                                             resource_endpoint + "\'",
                                             relation_type="has_" +
                                             resource['@type'],
                                             label_dest="objects" +
                                             resource['@type'],
                                             where_dest="id : \'" +
                                             resource['@id'] + "\'")
            return
        except ValueError as e:
            # Second Case - When processing a GET for a Colletion
            try:
                entrypoint, resource_endpoint = url.split('/')
                redis_collection_id = self.vocabulary + \
                    ":" + entrypoint + \
                    "/" + resource_endpoint

                self.graph_utils.update(
                    match="collection",
                    where="id='{}'".format(redis_collection_id),
                    set="members = \"{}\"".format(str(resource["members"])))
                return

            # Third Case - When processing a valid GET that is not compatible-
            # with the Redis Hydra structure, only returns response
            except Exception as e:
                logger.info("No modification to Redis was made")
                return

    def put_processing(self, url, new_object) -> None:
        """Synchronize Redis upon new PUT operations
        :param url: URL for the resource to be created.
        :return: None.
        """
        # Simply call sync_get to add the resource to the collection at Redis
        self.get_processing(url, new_object)
        return

    def post_processing(self, url, resource, updated_object) -> None:
        """Synchronize Redis upon new POST operations
        :param url: URL for the resource to be updated.
        :return: None.
        """
        # Simply call sync_get to add the resource to the collection at Redis
        self.get_processing(url, updated_object)
        return

    def delete_processing(self, url) -> None:
        """Synchronize Redis upon new DELETE operations
        :param url: URL for the resource deleted.
        :return: None.
        """
        url = url.rstrip('/').replace(self.entrypoint_url, "EntryPoint")
        entrypoint, resource_endpoint, resource_id = url.split('/')

        # Building the the collection id, i.e. vocab:Entrypoint/Collection
        redis_collection_id = self.vocabulary + \
            ":" + entrypoint + \
            "/" + resource_endpoint

        collection_members = self.graph_utils.read(
            match="collection",
            where="id='{}'".format(redis_collection_id),
            ret="members")

        # Accessing the members with redis-set response structure and deleting
        collection_members = eval(collection_members[0][1][0].decode())
        for member in collection_members:
            if resource_id in member['@id']:
                collection_members.remove(member)

        self.graph_utils.update(
            match="collection",
            where="id='{}'".format(redis_collection_id),
            set="members = \"{}\"".format(str(collection_members)))
        return


if __name__ == "__main__":
    requests = Requests("http://localhost:8080/serverapi",
                        RedisProxy())

    logger.info(requests.get("http://localhost:8080/serverapi/DroneCollection/"))

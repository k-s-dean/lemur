"""
.. module: lemur.plugins.lemur_java.plugin
    :platform: Unix
    :copyright: (c) 2015 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.

.. moduleauthor:: Kevin Glisson <kglisson@netflix.com>
"""
import subprocess

from flask import current_app

from lemur.utils import mktempfile, mktemppath
from lemur.plugins.bases import ExportPlugin
from lemur.plugins import lemur_java as java
from lemur.common.utils import get_psuedo_random_string


def run_process(command):
    """
    Runs a given command with pOpen and wraps some
    error handling around it.
    :param command:
    :return:
    """
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()

    if p.returncode != 0:
        current_app.logger.debug(" ".join(command))
        current_app.logger.error(stderr)
        raise Exception(stderr)


def split_chain(chain):
    """
    Split the chain into individual certificates for import into keystore

    :param chain:
    :return:
    """
    certs = []
    lines = chain.split('\n')

    cert = []
    for line in lines:
        cert.append(line + '\n')
        if line == '-----END CERTIFICATE-----':
            certs.append("".join(cert))
            cert = []

    return certs


def create_truststore(cert, chain, jks_tmp, alias, passphrase):
    with mktempfile() as cert_tmp:
        with open(cert_tmp, 'w') as f:
            f.write(cert)

        run_process([
            "keytool",
            "-importcert",
            "-file", cert_tmp,
            "-keystore", jks_tmp,
            "-alias", "{0}_cert".format(alias),
            "-storepass", passphrase,
            "-noprompt"
        ])

        # Import the entire chain
        for idx, cert in enumerate(split_chain(chain)):
            with mktempfile() as c_tmp:
                with open(c_tmp, 'w') as f:
                    f.write(cert)

                # Import signed cert in to JKS keystore
                run_process([
                    "keytool",
                    "-importcert",
                    "-file", c_tmp,
                    "-keystore", jks_tmp,
                    "-alias", "{0}_cert_{1}".format(alias, idx),
                    "-storepass", passphrase,
                    "-noprompt"
                ])


def create_keystore(cert, jks_tmp, key, alias, passphrase):
    with mktempfile() as key_tmp:
        with open(key_tmp, 'w') as f:
            f.write(key)

        # Create PKCS12 keystore from private key and public certificate
        with mktempfile() as cert_tmp:
            with open(cert_tmp, 'w') as f:
                f.write(cert)

            with mktempfile() as p12_tmp:
                run_process([
                    "openssl",
                    "pkcs12",
                    "-export",
                    "-name", alias,
                    "-in", cert_tmp,
                    "-inkey", key_tmp,
                    "-out", p12_tmp,
                    "-password", "pass:{}".format(passphrase)
                ])

                # Convert PKCS12 keystore into a JKS keystore
                run_process([
                    "keytool",
                    "-importkeystore",
                    "-destkeystore", jks_tmp,
                    "-srckeystore", p12_tmp,
                    "-srcstoretype", "PKCS12",
                    "-alias", alias,
                    "-srcstorepass", passphrase,
                    "-deststorepass", passphrase
                ])


class JavaTruststoreExportPlugin(ExportPlugin):
    title = 'Java Truststore (JKS)'
    slug = 'java-truststore-jks'
    description = 'Attempts to generate a JKS truststore'
    requires_key = False
    version = java.VERSION

    author = 'Kevin Glisson'
    author_url = 'https://github.com/netflix/lemur'

    options = [
        {
            'name': 'alias',
            'type': 'str',
            'required': False,
            'helpMessage': 'Enter the alias you wish to use for the truststore.',
        },
        {
            'name': 'passphrase',
            'type': 'str',
            'required': False,
            'helpMessage': 'If no passphrase is given one will be generated for you, we highly recommend this. Minimum length is 8.',
            'validation': ''
        },
    ]

    def export(self, body, chain, key, options, **kwargs):
        """
        Generates a Java Truststore

        :param key:
        :param chain:
        :param body:
        :param options:
        :param kwargs:
        """

        if self.get_option('alias', options):
            alias = self.get_option('alias', options)
        else:
            alias = "blah"

        if self.get_option('passphrase', options):
            passphrase = self.get_option('passphrase', options)
        else:
            passphrase = get_psuedo_random_string()

        with mktemppath() as jks_tmp:
            create_truststore(body, chain, jks_tmp, alias, passphrase)

            with open(jks_tmp, 'rb') as f:
                raw = f.read()

        return "jks", passphrase, raw


class JavaKeystoreExportPlugin(ExportPlugin):
    title = 'Java Keystore (JKS)'
    slug = 'java-keystore-jks'
    description = 'Attempts to generate a JKS keystore'
    version = java.VERSION

    author = 'Kevin Glisson'
    author_url = 'https://github.com/netflix/lemur'

    options = [
        {
            'name': 'passphrase',
            'type': 'str',
            'required': False,
            'helpMessage': 'If no passphrase is given one will be generated for you, we highly recommend this. Minimum length is 8.',
            'validation': ''
        },
        {
            'name': 'alias',
            'type': 'str',
            'required': False,
            'helpMessage': 'Enter the alias you wish to use for the keystore.',
        }
    ]

    def export(self, body, chain, key, options, **kwargs):
        """
        Generates a Java Keystore

        :param key:
        :param chain:
        :param body:
        :param options:
        :param kwargs:
        """

        if self.get_option('passphrase', options):
            passphrase = self.get_option('passphrase', options)
        else:
            passphrase = get_psuedo_random_string()

        if self.get_option('alias', options):
            alias = self.get_option('alias', options)
        else:
            alias = "blah"

        with mktemppath() as jks_tmp:
            if not key:
                raise Exception("Unable to export, no private key found.")

            create_truststore(body, chain, jks_tmp, alias, passphrase)
            create_keystore(body, jks_tmp, key, alias, passphrase)

            with open(jks_tmp, 'rb') as f:
                raw = f.read()

        return "jks", passphrase, raw

import logging
import os
from collections import defaultdict

from google.appengine.ext import ndb
from werkzeug import parse_options_header

import flask


logger = logging.getLogger(__name__)


def index():
    """
    Kibble index view. Lists the registered classes and views.
    """
    return flask.render_template('kibble/index.html')


def upload():
    payload = {}

    for field, filedata in flask.request.files.iteritems():
        parsed_header = parse_options_header(filedata.content_type)
        payload[field] = {
            'blobkey': parsed_header[1]['blob-key'],
            'filename': filedata.filename,
        }

    return flask.jsonify(payload)


class Kibble(flask.Blueprint):
    def __init__(self, name, import_name, auth, label=None, **kwargs):
        """
        The central point of the Kibble admin. Manages permissions of views.

        :param name: The blueprint name.
        :param import_name: The importable name.
        :param auth: A ``flask_kibble.Authenticator`` subclass to provide
            authentication and permissions.
        :param label: The label of the Kibble admin. Will default to the name.
        """

        kwargs.setdefault(
            'template_folder',
            os.path.join(os.path.dirname(__file__), 'templates'))

        kwargs.setdefault(
            'static_folder',
            os.path.join(os.path.dirname(__file__), 'static'))

        super(Kibble, self).__init__(name, import_name, **kwargs)
        self.label = label or self.name.title()
        self.auth = auth

        self.registry = defaultdict(dict)

        self.add_url_rule('/', view_func=index, endpoint='index')
        self.add_url_rule('/_upload/',
                          view_func=upload,
                          endpoint='upload',
                          methods=['POST'])

        self.record_once(self._register_urlconverter)

        self.before_request(self._before_request)
        self.context_processor(self._context_processor)

    def register_view(self, view_class):
        """
        Register a class with the Kibble blueprint.

        :param view_class: A KibbleView class

        :raises ValueError: When the same (Class,Action) pair is already
            registered.
        """
        action = view_class.action
        kind = view_class.kind()
        path = view_class.path()

        # Check for duplicates
        if action in self.registry[path]:
            raise ValueError("%s already has view for %s:%s" % (
                self, path, action))

        view_func = view_class.as_view(view_class.view_name())
        ancest_kinds = [x._get_kind() for x in view_class.ancestors]

        key = "<ndbkey({0}):key>".format(",".join([
            "'%s'" % x for x in ancest_kinds + [kind]]))
        ancestor_key = "<ndbkey({0}):ancestor_key>".format(
            ",".join(["'%s'" % x for x in ancest_kinds]))

        for pattern, defaults in view_class.url_patterns():
            self.add_url_rule(
                pattern.format(
                    key=key,
                    ancestor_key=ancestor_key,
                    kind=kind,
                    kind_lower=kind.lower(),
                    action=action),
                methods=view_class._methods,
                defaults=defaults,
                view_func=view_func)

        self.registry[path][action] = view_class

    def autodiscover(self, paths, models=None):
        """
        Automatically register all Kibble views under ``path``.

        :param paths: The module paths to search under.
        :param models: A list of model kinds (either a ``ndb.Model`` subclass
            or a string) (Optional)
        """
        from werkzeug.utils import find_modules, import_string
        from .base import KibbleMeta

        all_models = models is None
        models = [
            (x._kind() if isinstance(x, ndb.Model) else x)
            for x in models or []]

        for p in paths:
            for mod in find_modules(p, True, True):
                logger.debug("Autodiscover: %s", mod)
                import_string(mod)

        for view in KibbleMeta._autodiscover:
            if view.model and (all_models or view.kind() in models):
                self.register_view(view)
            else:
                logger.debug("Autodiscover skipping: %r", view)

    def _context_processor(self):
        return {'kibble': self}

    @classmethod
    def _register_urlconverter(self, setup_state):
        from .util.url_converter import NDBKeyConverter
        app = setup_state.app
        app.url_map.converters.setdefault('ndbkey', NDBKeyConverter)

    def _before_request(self):
        flask.g.kibble = self         # Set global var

        if not self.auth.is_logged_in():
            # User not logged in, redirect to the login url.
            logger.debug("User is not logged in.")
            flask.flash("You are not logged in.", 'warning')
            return flask.redirect(self.auth.get_login_url())

        view_func = flask.current_app.view_functions[flask.request.endpoint]
        view_class = getattr(view_func, 'view_class', None)

        if view_class:
            # for CBVs, use the model and action parameters.
            model = view_class.model
            action = view_class.action
        else:
            # For non-CBVs, use the view name as the permission values.
            model = None
            action = view_func.__name__

        if not self.auth.has_permission_for(
                model, action,
                **flask.request.view_args):

            logger.debug("User is missing permission for %r",
                         flask.request.endpoint)
            return flask.render_template('kibble/403.html'), 403

    def url_for(self, model, action, instance=None):
        """
        Get the URL for a specific Model/Action/Instance.

        If the view isn't registered, returns an empty string.

        :param model: A ``ndb.Model`` subclass or string. For ancestral
                      objects, this can be a path.
        :param action: The name of the action to link to. e.g. 'create'.
        :param instance: A :py:class:`ndb.Model` instance or
            :py:class:`ndb.Key` to link to.
        """
        if isinstance(model, type) and issubclass(model, ndb.Model):
            model = model._get_kind()

        view = self.registry.get(model, {}).get(action)

        if not view:
            return ""

        return view.url_for(instance, blueprint=self.name)


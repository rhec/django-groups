import sys

from django.shortcuts import render_to_response
from django.conf.urls.defaults import patterns, url as urlpattern
from django.core.urlresolvers import RegexURLPattern, RegexURLResolver, reverse as dreverse

from django.contrib.contenttypes.models import ContentType


class ContentBridge(object):
    
    def __init__(self, group_model, content_app_name=None, legacy=False):
        self.parent_bridge = None
        self.group_model = group_model
        
        if content_app_name is None:
            self.content_app_name = group_model._meta.app_label
            self.legacy_mode = legacy
        else:
            self.content_app_name = content_app_name
            self.legacy_mode = True
        
        # attach the bridge to the model itself. we need to access it when
        # using groupurl to get the correct prefix for URLs for the given
        # group.
        self.group_model.content_bridge = self
    
    def include_urls(self, module_name, url_prefix, kwargs=None):
        if kwargs is None:
            kwargs = {}
        
        prefix = self.content_app_name
        
        __import__(module_name)
        module = sys.modules[module_name]
        
        if hasattr(module, "bridge"):
            module.bridge.parent_bridge = self
        
        urls = []
        
        for url in module.urlpatterns:
            extra_kwargs = {"bridge": self}
            
            if isinstance(url, RegexURLPattern):
                regex = url_prefix + url.regex.pattern.lstrip("^")
                
                if url._callback:
                    callback = url._callback
                else:
                    callback = url._callback_str
                
                if url.name:
                    name = url.name
                else:
                    # @@@ this seems sketchy
                    name = ""
                name = "%s_%s" % (prefix, name)
                
                extra_kwargs.update(kwargs)
                extra_kwargs.update(url.default_args)
                
                urls.append(urlpattern(regex, callback, extra_kwargs, name))
            else:
                # i don't see this case happening much at all. this case will be
                # executed likely if url is a RegexURLResolver. nesting an include
                # at the content object level may not be supported, but maybe the
                # code below works. i don't have time to test it, but if you are
                # reading this because something is broken then give it a shot.
                # then report back :-)
                raise Exception("ContentBridge.include_urls does not support a nested include.")
                
                # regex = url_prefix + url.regex.pattern.lstrip("^")
                # urlconf_name = url.urlconf_name
                # extra_kwargs.update(kwargs)
                # extra_kwargs.update(url.default_kwargs)
                # final_urls.append(urlpattern(regex, [urlconf_name], extra_kwargs))
        
        return patterns("", *urls)
    
    @property
    def _url_name_prefix(self):
        parent_prefix = ""
        
        if self.parent_bridge is not None:
            parent_prefix = "%s_" % self.parent_bridge._url_name_prefix
        
        return "%s%s" % (parent_prefix, self.content_app_name)
    
    def reverse(self, view_name, group, kwargs=None):
        if kwargs is None:
            kwargs = {}
        
        final_kwargs = {}
        
        final_kwargs.update(group.get_url_kwargs())
        final_kwargs.update(kwargs)
        
        return dreverse("%s_%s" % (self._url_name_prefix, view_name), kwargs=final_kwargs)
    
    def render(self, template_name, context, context_instance=None):
        # @@@ this method is practically useless -- consider removing it.
        ctype = ContentType.objects.get_for_model(self.group_model)
        return render_to_response([
            "%s/%s/%s" % (ctype.app_label, self.content_app_name, template_name),
            "%s/%s" % (self.content_app_name, template_name),
        ], context, context_instance=context_instance)
    
    def group_base_template(self, template_name="content_base.html"):
        return "%s/%s" % (self.content_app_name, template_name)
    
    def get_group(self, *args, **kwargs):
        
        lookup_params = {}
        
        if self.parent_bridge is not None:
            parent_group = self.parent_bridge.get_group(**kwargs)
            lookup_params.update({
                "content_type": ContentType.objects.get_for_model(parent_group),
                "object_id": parent_group.pk,
            })
        else:
            parent_group = None
        
        if self.legacy_mode:
            slug = args[0]
        else:
            slug = kwargs.get("%s_slug" % self.group_model._meta.object_name.lower())
        
        lookup_params.update({
            "slug": slug,
        })
        
        group = self.group_model._default_manager.get(**lookup_params)
        
        if parent_group:
            # cache parent_group on GFK to prevent database hits later on
            group.group = parent_group
        
        return group
        
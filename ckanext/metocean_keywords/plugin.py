import ckan.plugins as p
import ckan.plugins.toolkit as toolkit
from collections import OrderedDict
from sortedcontainers import SortedDict
from ckanext.spatial.interfaces import ISpatialHarvester
from itertools import chain
from lxml import etree
import logging
import re
import json

log = logging.getLogger()

def filter_tag_names(tags, cf_standard_names=None, gcmd_keywords=None):
    """
    Takes a list of tags which to filter based upon the provided CF Standard
    Names and GCMD Keywords to be excluded and filters out
    any tags which have a display_name which is present in the set of values to
    be excluded.
    """
    excludes_set = set()
    if cf_standard_names:
        excludes_set.update(set(standard_name.lower() for standard_name in
                                cf_standard_names))
    if gcmd_keywords:
        gcmd_components = set(t.lower() for t in
                              split_gcmd_list(gcmd_keywords))
        excludes_set.update(gcmd_components)
    # return tag list of dicts without excluded tags deduplicated and sorted
    # against the tag "display_name"
    return sorted(map(dict, set(frozenset(list(d.items())) for d in tags if
                                d['display_name'].lower() not in excludes_set)
                     ), key=lambda d: d['display_name'])

def gcmd_keywords_to_multilevel_sorted_dict(gcmd_keywords,
                                            dict_factory=SortedDict,
                                            is_facet=False):

    gcmd_dict = dict_factory()
    if is_facet:
        prepped_kw = ((re.sub(r"\s*>\s*", ' > ',
                             re.sub(r"\s+", " ", kw)).upper(), count)
                    for kw, count in gcmd_keywords)
        for kw, count in prepped_kw:
            gcmd_levels = kw.split(' > ')
            current_hierarchy = gcmd_dict
            for level in gcmd_levels:
                if level not in current_hierarchy:
                    current_hierarchy[level] = dict_factory()
                    current_hierarchy[level].full_name = kw
                    current_hierarchy[level].count = count
                current_hierarchy = current_hierarchy[level]
    # TODO: eliminate repetition of code
    else:
        prepped_kw = (re.sub(r"\s*>\s*", ' > ', re.sub(r"\s+", " ", kw)).upper()
                    for kw in gcmd_keywords)
        for kw in prepped_kw:
            gcmd_levels = kw.split(' > ')
            current_hierarchy = gcmd_dict
            for level in gcmd_levels:
                if level not in current_hierarchy:
                    current_hierarchy[level] = dict_factory()
                current_hierarchy = current_hierarchy[level]

    # put into multilevel sorted dict.  Could possibly subclass defaultdict
    # for this?

    # now generate
    return gcmd_dict

def gcmd_generate(gcmd_keywords):
    return gcmd_to_ul(gcmd_keywords_to_multilevel_sorted_dict(gcmd_keywords),
                      ul_attrs={'class': 'tag-list tree'})

def gcmd_generate_facets(gcmd_keywords):
    def sort_gcmd(kw_in):
        kw_split = kw_in[0].split('>')
        # return the "root term", followed by the number of levels, followed
        # by the count descending (thus negative), followed by the last term
        return len(kw_split), -kw_in[1], kw_split[0], kw_split[-1]

    gcmd_facets = [(d['name'], d['count']) for d in gcmd_keywords]
    gcmd_facets.sort(key=sort_gcmd)
    return gcmd_keywords_to_multilevel_sorted_dict(gcmd_facets, OrderedDict,
                                                   True)


def gen_tree_ul(parent_li, prev_results, sub_key):
    new_hier = prev_results + [sub_key]
    exploded_kw = " > ".join(new_hier)
    anchor_attrs = {'class': 'tag',
                    'href': '/dataset?q=gcmd_keywords:"{}"'.format(exploded_kw)}
    gcmd_link = etree.SubElement(parent_li, 'a', anchor_attrs)
    gcmd_link.text = sub_key
    return new_hier


def gen_facet_ul(parent_li, prev_results, sub_key):
    new_hier = prev_results + [sub_key[0]]
    exploded_kw = " > ".join(new_hier)
    anchor_attrs = {'href': '/dataset?q=gcmd_keywords:"{}"'.format(exploded_kw)}
    gcmd_link = etree.SubElement(parent_li, 'a', anchor_attrs)
    label_span = etree.SubElement(gcmd_link, "span", {"class": "item-label"})
    label_span.text = sub_key[0]
    return new_hier


def gcmd_to_ul(gcmd_dict, elem=None, prev_results=None,
               list_gen_fun=gen_tree_ul,
               base_ul_attrs={'class': 'tag-list tree'},
               ul_attrs={'class': 'tag-list'}):
    # avoid side effects with mutable args duplicating same tree several times
    if prev_results is None:
        prev_results = []
    if elem is None:
        elem = etree.Element('ul', base_ul_attrs)
    for sub_key, sub_dict in list(gcmd_dict.items()):
        gcmd_list = etree.SubElement(elem, 'li')

        new_hier = list_gen_fun(gcmd_list, prev_results, sub_key)
        if sub_dict:
            new_ul = etree.SubElement(gcmd_list, 'ul', {'class': 'tag-list'})
            gcmd_to_ul(sub_dict, new_ul, new_hier)

    # operates on side effects, so if the base recursion case, return
    # the generated XML string.
    if not prev_results:
        return etree.tostring(elem, pretty_print=True, encoding=str)

def split_gcmd_list(tags):
    return chain(*[re.split(r'\s*>\s*', t.strip()) for t in tags])

def split_gcmd_tags(tags):
    """
    Splits any GCMD keyword components (usually separated by " > " into
    separate, unique tags. Returns a list of tags if successful, or None
    if the tags ran into an exception
    """
    #TODO: should we also store the full GCMD keywords as extras and in
    #           Solr?
    try:
        unique_tags = set(split_gcmd_list(tags))
        # limit tags to 100 chars so we don't get a database error
        return [{'name': val[:100]} for val in sorted(unique_tags)
                if val != '']
    except:
        log.exception("Error occurred while splitting GCMD tags:")
        return None


class MetoceanKeywordsPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IRoutes, inherit=True)
    p.implements(p.IPackageController, inherit=True)
    p.implements(ISpatialHarvester, inherit=True)
    p.implements(p.IFacets, inherit=True)

    def before_index(self, data_dict):
        # write GCMD Keywords and CF Standard Names to corresponding solr
        # multi-index fields
        data_modified = data_dict.copy()
        for field_name in ('cf_standard_names', 'gcmd_keywords'):
            extras_str = data_dict.get("extras_{}".format(field_name))
            if extras_str is not None:
                try:
                    extras_parse = [e.strip() for e in
                                    json.loads(extras_str)]
                except ValueError:
                    log.exception("Can't parse {} from JSON".format(field_name))
                else:
                    data_modified[field_name] = extras_parse
        return data_modified

    def dataset_facets(self, facets_dict, package_type):
        facets_dict['cf_standard_names'] = p.toolkit._('CF Standard Names')
        facets_dict['gcmd_keywords'] = p.toolkit._('GCMD Keywords')
        return facets_dict

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("public", "metocean_keywords")

    def get_helpers(self):
        '''
        Defines a set of callable helpers for the JINJA templates.
        '''
        return {
            "filter_tag_names": filter_tag_names,
            "gcmd_generate": gcmd_generate,
            "gcmd_generate_facets": gcmd_generate_facets,
        }

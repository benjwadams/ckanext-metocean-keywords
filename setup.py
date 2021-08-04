entry_points="""
    [ckan.plugins]
    example_iauthfunctions=ckanext.metocean_keywords.plugin:MetoceanKeywordsPlugin
"""
install_requires=[
    # TODO: is this necessary with newer Python versions sorting dict
    # automatically?
    "sortedcontainers"
],

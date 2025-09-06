def chain_from_iterable(list_of_generators):
  """
  Chains a list of generators into a single generator.
  """
  for gen in list_of_generators:
    for item in gen:
      yield item
import re
import sys
from StringIO import StringIO

from elements import Element

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import guess_lexer, guess_lexer_for_filename

ELEMENT = '%'
ID = '#'
CLASS = '.'
DOCTYPE = '!!!'

HTML_COMMENT = '/'
CONDITIONAL_COMMENT = '/['
HAML_COMMENTS = ['-#', '=#']

VARIABLE = '='
TAG = '-'

COFFEESCRIPT_FILTERS = [':coffeescript', ':coffee']
JAVASCRIPT_FILTER = ':javascript'
CSS_FILTER = ':css'
STYLUS_FILTER = ':stylus'
PLAIN_FILTER = ':plain'
PYTHON_FILTER = ':python'
CDATA_FILTER = ':cdata'
PYGMENTS_FILTER = ':highlight'

ELEMENT_CHARACTERS = (ELEMENT, ID, CLASS)

HAML_ESCAPE = '\\'

def create_node(haml_line):
    stripped_line = haml_line.strip()
    
    if not stripped_line:
        return None
        
    if stripped_line[0] == HAML_ESCAPE:
        return HamlNode(haml_line.replace(HAML_ESCAPE, '', 1))
        
    if stripped_line.startswith(DOCTYPE):
        return DoctypeNode(haml_line)
        
    if stripped_line[0] in ELEMENT_CHARACTERS:
        return ElementNode(haml_line)
    
    if stripped_line[0:len(CONDITIONAL_COMMENT)] == CONDITIONAL_COMMENT:
        return ConditionalCommentNode(haml_line)
        
    if stripped_line[0] == HTML_COMMENT:
        return CommentNode(haml_line)
    
    for comment_prefix in HAML_COMMENTS:
        if stripped_line.startswith(comment_prefix):
            return HamlCommentNode(haml_line)
    
    if stripped_line[0] == VARIABLE:
        return VariableNode(haml_line)

    if stripped_line[0] == TAG:
        return TagNode(haml_line)
    
    if stripped_line == JAVASCRIPT_FILTER:
        return JavascriptFilterNode(haml_line)
    
    if stripped_line in COFFEESCRIPT_FILTERS:
        return CoffeeScriptFilterNode(haml_line)
        
    if stripped_line == CSS_FILTER:
        return CssFilterNode(haml_line)
    
    if stripped_line == STYLUS_FILTER:
        return StylusFilterNode(haml_line)

    if stripped_line == PLAIN_FILTER:
        return PlainFilterNode(haml_line)
        
    if stripped_line == PYTHON_FILTER:
        return PythonFilterNode(haml_line)
    
    if stripped_line == CDATA_FILTER:
        return CDataFilterNode(haml_line)
		
    if stripped_line == PYGMENTS_FILTER:
        return PygmentsFilterNode(haml_line)
    
    return HamlNode(haml_line.rstrip())

class RootNode:
    
    def __init__(self):
        self.indentation = -1
        self.internal_nodes = []
    
    def parent(self,node):
        if (node == None):
            return None

        if (self._should_go_inside_last_node(node)):
            ret = self.internal_nodes[-1].parent(node)
            return ret
        else:
            return self

    def add_node(self, node):
        if (node == None):
            return
        
        if (self._should_go_inside_last_node(node)):
            self.internal_nodes[-1].add_node(node)
        else:
            self.internal_nodes.append(node)
    
    def _should_go_inside_last_node(self, node):
        return len(self.internal_nodes)>0 and (node.indentation > self.internal_nodes[-1].indentation
            or (node.indentation == self.internal_nodes[-1].indentation and self.internal_nodes[-1].should_contain(node)))
    
    def render(self):
        return self.render_internal_nodes()
    
    def render_internal_nodes(self):
        nodes = [node.render() for node in self.internal_nodes]
        
        # Outer Whitespace removal
        for i, node in enumerate(self.internal_nodes):
            if hasattr(node, 'element') and node.element.nuke_outer_whitespace:
                if i>0:
                    # If node has previous sibling, strip whitespace after previous sibling
                    nodes[i-1] = nodes[i-1].rstrip()
                else:
                    # If not, whitespace comes from it's parent node,
                    # so don't print whitespace before the node
                    self.pre_space = ''
                    self.newlines = 0

                nodes[i] = nodes[i].strip()

                if i<len(self.internal_nodes)-1:
                    # If we have a sibling to the right, left-strip it
                    nodes[i+1] = nodes[i+1].lstrip()
                else:
                    # We're the last sibling, print nothing after
                    self.post_space = ''
                    self.newlines = 0

        return ''.join(nodes)
    
    def has_internal_nodes(self):
        return len(self.internal_nodes) > 0
    
    def should_contain(self, node):
        return False
      
        
class HamlNode(RootNode):
    
    def __init__(self, haml):
        RootNode.__init__(self)
        self.haml = haml.strip()
        # For preserving whitespace by tracking the number of blank lines after the node in the HAML file
        self.newlines = 0
        self.raw_haml = haml
        self.indentation = (len(haml) - len(haml.lstrip()))
        self.spaces = ''.join(haml[0] for i in range(self.indentation))

        self.pre_space = '\n'
        self.post_space = self.spaces

    def render(self):
        return ''.join([self.spaces, self.haml, '\n'*(self.newlines+1), self.render_internal_nodes()])

    def __repr__(self):
        return '(%s) %s' % (self.__class__, self.haml)


class ElementNode(HamlNode):
    def __init__(self, haml):
        HamlNode.__init__(self, haml)
        self.django_variable = False

    def render(self):
        return self._render_tag()
    
    def _render_tag(self):
        self.element = Element(self.haml)
        self.django_variable = self.element.django_variable
        return self._generate_html(self.element)
        
    def _generate_html(self, element):
        if self.indentation > 0:
            result = "%s<%s" % (self.spaces, element.tag) 
        else:
            result = "<%s" % element.tag 

        if element.id:
            result += " id='%s'" % element.id 
        if element.classes:
            result += " class='%s'" % element.classes 
        if element.attributes:
            result += ' ' + element.attributes            
            
        content = self._render_tag_content(element.inline_content)

        if element.nuke_inner_whitespace:
            content = content.strip()
        
        if element.self_close and not content:
            result += " />" + "\n"*(self.newlines+1)
        else:
            # If element content is inline, we should put any newlines after the tag
            if element.inline_content:
                nl = '\n'*(self.newlines+1) if not element.nuke_outer_whitespace else ''
                result += ">%s</%s>%s" % (content, element.tag, nl)
            else:
                nl = '\n'*self.newlines if not element.nuke_inner_whitespace else ''
                result += ">%s%s</%s>\n" % (nl, content, element.tag)

        return result

    def _render_tag_content(self, current_tag_content):
        if self.has_internal_nodes():
            # Must render internal nodes first so that pre_space and post_space are set correctly
            content = self.render_internal_nodes()
            current_tag_content = '%s%s%s' % (self.pre_space, content, self.post_space)
        if current_tag_content == None:
            current_tag_content = ''
        if self.django_variable:
            current_tag_content = "{{ " + current_tag_content.strip() + " }}"
        current_tag_content = re.sub(r'#\{([a-zA-Z0-9\.\_]+)\}', r'{{ \1 }}', current_tag_content)
        return current_tag_content


class CommentNode(HamlNode):
    
    def render(self):
        content = ''
        if self.has_internal_nodes():
            content = '\n' + self.render_internal_nodes()
        else:
            content = self.haml.lstrip(HTML_COMMENT).strip() + ' '
        
        return "<!-- %s-->\n" % content

class ConditionalCommentNode(HamlNode):
    
    def render(self):
        conditional = self.haml[1: self.haml.index(']')+1 ]
        content = ''
        content = content + self.haml[self.haml.index(']')+1:]
        space = ''
        if self.has_internal_nodes():
            content = self.render_internal_nodes()
            space = self.pre_space
        return "<!--%s>%s%s%s<![endif]-->" % (conditional, space, content, self.post_space)
        

class DoctypeNode(HamlNode):
    
    def render(self):
        doctype = self.haml.lstrip(DOCTYPE).strip()
        
        if doctype == "":
            content = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">'
        if doctype == "Strict":
            content = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
        if doctype == "Frameset":
            content = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Frameset//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-frameset.dtd">'
        if doctype == "5":
            content = '<!DOCTYPE html>'
        if doctype == "1.1":
            content = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
        
        return "%s%s" % (content, '\n'*(self.newlines+1))

class HamlCommentNode(HamlNode):
    
    def render(self):
        return '\n'*self.newlines


class VariableNode(ElementNode):
    def __init__(self, haml):
        ElementNode.__init__(self, haml)
        self.django_variable = True
    
    def render(self):
        tag_content = self.haml.lstrip(VARIABLE)
        return "%s%s%s" % (self.spaces, self._render_tag_content(tag_content), '\n'*(self.newlines+1))


class TagNode(HamlNode):
    self_closing = {'for':'endfor',
                    'if':'endif',
                    'ifchanged':'endifchanged',
                    'ifequal':'endifequal',
                    'ifnotequal':'endifnotequal',
                    'block':'endblock',
                    'filter':'endfilter',
                    'autoescape':'endautoescape',
                    'with':'endwith',
                    'blocktrans': 'endblocktrans',
                    'spaceless': 'endspaceless',
                    'comment': 'endcomment',
                    'cache': 'endcache',
                    'localize': 'endlocalize',
                    'compress': 'endcompress'}
    may_contain = {'if':['else', 'elif'], 
                   'ifchanged':'else',
                   'ifequal':'else',
                   'ifnotequal':'else',
                   'for':'empty', 
                   'with':'with'}
    
    def __init__(self, haml):
        HamlNode.__init__(self, haml)
        self.tag_statement = self.haml.lstrip(TAG).strip()
        self.tag_name = self.tag_statement.split(' ')[0]
        
        if (self.tag_name in self.self_closing.values()):
            raise TypeError("Do not close your Django tags manually.  It will be done for you.")
    
    def render(self):
        internal = self.render_internal_nodes()
        output = "%s{%% %s %%}%s%s%s" % (self.spaces, self.tag_statement, '\n'*self.newlines, self.pre_space, internal)
        if (self.tag_name in self.self_closing.keys()):
            output += '%s{%% %s %%}\n' % (self.post_space, self.self_closing[self.tag_name])
        return output
    
    def should_contain(self, node):
        return isinstance(node,TagNode) and node.tag_name in self.may_contain.get(self.tag_name,'')


class FilterNode(HamlNode):
  def add_node(self, node):
      if (node == None):
          return
      else:
          self.internal_nodes.append(node)


class PlainFilterNode(FilterNode):
    def render(self):
        if self.internal_nodes:
            first_indentation = self.internal_nodes[0].indentation
        return '\n'*self.newlines + "".join([ node.raw_haml[first_indentation:] + '\n'*(node.newlines+1) for node in self.internal_nodes])


class PythonFilterNode(FilterNode):
    def render(self):
        code = compile("".join([node.raw_haml.strip() + '\n' for node in self.internal_nodes]), "", "exec")
        
        buffer = StringIO()
        sys.stdout = buffer
        exec code
        # restore the original stdout
        sys.stdout = sys.__stdout__
        return buffer.getvalue()


class JavascriptFilterNode(FilterNode):
    def render(self):
        output = '<script type=\'text/javascript\'>\n// <![CDATA['
        output += '\n'*(self.newlines+1)
        output += "".join((''.join((node.spaces, node.haml, '\n'*(node.newlines+1))) for node in self.internal_nodes))
        output += '// ]]>\n</script>\n'
        return output
        
        
class CoffeeScriptFilterNode(FilterNode):
    def render(self):
        output = '<script type=\'text/coffeescript\'>\n#<![CDATA['
        output += '\n'*(self.newlines+1)
        output += ''.join([''.join((node.raw_haml,'\n'*(node.newlines+1))) for node in self.internal_nodes])
        output += '#]]>\n</script>\n'
        return output


class CssFilterNode(FilterNode):
    def render(self):
        output = '<style type=\'text/css\'>\n/*<![CDATA[*/'
        output += '\n'*(self.newlines+1)
        output += "".join((''.join((node.spaces, node.haml,'\n'*(node.newlines+1))) for node in self.internal_nodes))
        output += '/*]]>*/\n</style>\n'
        return output


class StylusFilterNode(FilterNode):
    def render(self):
        output = '<style type=\'text/stylus\'>\n/*<![CDATA[*/'
        output += '\n'*(self.newlines+1)
        first_indentation = self.internal_nodes[0].indentation
        output += ''.join([''.join((node.raw_haml[first_indentation:],'\n'*(node.newlines+1))) for node in self.internal_nodes])
        output += '/*]]>*/\n</style>\n'
        return output


class CDataFilterNode(FilterNode):
    def render(self):
        output = self.spaces + '<![CDATA['
        output += '\n'*(self.newlines+1)
        output += ''.join((''.join((node.spaces, node.haml,'\n'*(node.newlines+1))) for node in self.internal_nodes))
        output += self.spaces + ']]>\n'
        return output
		
class PygmentsFilterNode(FilterNode):
    def render(self):
        output = self.spaces
        output += highlighter(self.haml, guess_lexer(self.haml), HtmlFormatter())	
        return output

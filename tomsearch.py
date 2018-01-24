"""Tom's Searching Thingy
See README for more details
"""
import json
import sys
import cmd
import itertools
import unittest

from pprint import pprint

## Magic strings
# Field names
FIELD_ASSIGNEE_ID = "assignee_id"
FIELD_SUBMITTER_ID = "submitter_id"
FIELD_ID = "_id"
FIELD_ORGANIZATION_ID = "organization_id"
FIELD_SUBJECT = "subject"
FIELD_NAME = "name"
FIELD_TAGS = "tags"

## Magic Numbers
# Limit search results to show this many
MAX_RESULTS_SHOW = 30

## Global vars
# Vars for data lookup
TICKETS = None
ORGS = None
USERS = None
SEARCH_TYPES = None


## Class definitions
# Exceptions
class FailedException(Exception):
    """Exception to signify an exception that was presented to the user already"""
    pass

class ExitException(Exception):
    """Exception to raise a clean exit"""
    pass

# Result classes
class ResultValue(object):
    """Base Class representing a single result of the search"""
    def __init__(self, valuedict):
        self.valuedict = valuedict

    def present(self):
        """Tell the result to print itself to stdout"""
        pprint(self.valuedict)

class OrganizationResult(ResultValue):
    """Single result of a Organization search"""
    def __init__(self, values, usernames, ticketnames):
        super().__init__(values)
        self.usernames = usernames
        self.ticketnames = ticketnames

    def present(self):
        domains = "\n                ".join(self.valuedict["domain_names"])
        tags = ", ".join(self.valuedict[FIELD_TAGS])
        outp = """          Name: {0[name]}
            id: {0[_id]:10d}   ({0[external_id]})
           URL: {0[url]}
  domain_names: {1}
    created at: {0[created_at]}
       Details: {0[details]}
shared tickets: {0[shared_tickets]}
          tags: {2}""".format(self.valuedict,
                              domains,
                              tags)
        print(outp)
        if self.usernames:
            print(" Users:")
            for user in self.usernames:
                print("   * {}".format(user))
        if self.ticketnames:
            print(" Tickets:")
            for ticket in self.ticketnames:
                print("   * {}".format(ticket))

class TicketResult(ResultValue):
    """Represent a result of a ticket search"""
    def __init__(self, valuedict, org_name, submitter_name, assignee_name):
        super().__init__(valuedict)
        self.org_name = org_name
        self.submitter_name = submitter_name
        self.assignee_name = assignee_name

    def present(self):
        outp = """         Subject: {0[subject]}
              id: {0[_id]}    ({0[external_id]})
    organization: {0[organization_id]}    ({2})
            type: {0[type]}
       submitter: {0[submitter_id]}   ({3})
        assignee: {0[assignee_id]}   ({4})
     description: {0[description]}
        priority: {0[priority]}
          status: {0[status]}
            tags: {1}
             url: {0[url]}
      created_at: {0[created_at]:30.30s} due: {0[due_at]} 
             via: {0[via]}""".format(self.valuedict,
                                     ", ".join(self.valuedict[FIELD_TAGS]),
                                     presentation_name(self.org_name),
                                     presentation_name(self.submitter_name),
                                     presentation_name(self.assignee_name))
        print(outp)

class UserResult(ResultValue):
    """Represent a result for a user search"""
    def __init__(self, valuedict, org_name, assigned_ticket_names, submitted_ticket_names):
        super().__init__(valuedict)
        self.org_name = org_name
        self.assigned_ticket_names = assigned_ticket_names
        self.submitted_ticket_names = submitted_ticket_names

    def present(self):
        outp = """            Name: {0[name]:30.30s} (alias {0[alias]:10.10s})
              id: {0[_id]:<10d}     external_id: {0[external_id]}
 organization_id: {0[organization_id]} ({2}) 
      created_at: {0[created_at]:30.30s} last_login_at: {0[last_login_at]}
          active: {0[active]}
        verified: {0[verified]}
       suspended: {0[suspended]}
          shared: {0[shared]}
          locale: {0[locale]:20.20s}    timezone: {0[timezone]:30.30s} 
           email: {0[email]}
             url: {0[url]}
           phone: {0[phone]}
       signature: {0[signature]}
            role: {0[role]}
            tags: {1}""".format(self.valuedict,
                                ", ".join(self.valuedict[FIELD_TAGS]),
                                presentation_name(self.org_name))
        print(outp)
        if self.assigned_ticket_names:
            print(" Assigned Tickets:")
            for name in self.assigned_ticket_names:
                print("   * {}".format(name))
        if self.submitted_ticket_names:
            print(" Submitted Tickets:")
            for name in self.submitted_ticket_names:
                print("   * {}".format(name))

# Other classes

class ValidatedDictList(object):
    """Read in a json file and type check it from the given dict of key -> type
    Store the read in list of dictionaries inside this instance"""
    def __init__(self, filename, name, validatedict):
        self.name = name
        loadeddict = loadfile(filename)

        for val in loadeddict:
            for key, _type in validatedict.items():
                if key not in val:
                    # Not all entries are complete, so create a default
                    # This could later be extended to provide a default in the type defintion
                    # Never create a valid id though
                    if key.endswith("_id"):
                        val[key] = None
                    else:
                        val[key] = _type()
                    # Creating a default could cause problems depending on data needs
                    # So warn about it on load
                    print("{} Creating a default for {} {} record id {}".format(
                                filename, key, _type, val[FIELD_ID]),
                          file=sys.stderr)
                elif type(val[key]) is not _type:
                    fail("{} contained entry {} with key {} that was type {} instead of {}".format(
                            filename, val, key, type(val[key]), _type))
        self.values = loadeddict
        self.fields = validatedict


def presentation_name(name):
    """Return a name to present or 'None found' if it's missing"""
    if name:
        return name
    return "None found"

def fail(message):
    """Handle simple failures by printing a message and then raising an exception"""
    print(message)
    raise FailedException()

def find_one_field(validated_dict_list, match_field, match_value, return_field):
    """Return a list guaranteed to only have one value, returning an error message if needed
    :param return_field: The field name to return
    see find_all for definition of other parameters
    """
    results = find_all(validated_dict_list, match_field, match_value)
    if not results:
        return "None Found"
    elif len(results) == 1:
        return results[0][return_field]
    else:
        fail("found multiple results for value {} of {} in {} only expected one ".format(
            match_value, match_field, validated_dict_list.name))

def find_all(validated_dict_list, match_field, match_value):
    """ find_all - Core search function
    :param db:  A sequence of dictionary values
    :param match_field: the string of a field name to match on
    :param match_value: the value to match against
    """
    results = []
    if match_field not in validated_dict_list.fields.keys():
        fail("{} is not a valid key for {}".format(match_field, validated_dict_list.name))
    for value in validated_dict_list.values:
        if match_field in value:
            # To simplify searching generic fields, convert  data to string
            if str(value[match_field]) == str(match_value):
                results.append(value)
    return results

def field_from_values(values, field_name):
    """Return a generator of a certain field from a list of values"""
    return (value[field_name] for value in values)

def create_orgs_result(orgdict):
    """Create an OrganizationResult from a an organization diction entry"""
    org_id = orgdict.get(FIELD_ID)
    users = field_from_values(find_all(USERS, FIELD_ORGANIZATION_ID, org_id),
                              FIELD_NAME)
    tickets = field_from_values(find_all(TICKETS, FIELD_ORGANIZATION_ID, org_id),
                                FIELD_SUBJECT)
    return OrganizationResult(orgdict, users, tickets)

def loadfile(file):
    """ Load a Json file and return the contents"""
    err_message = None
    try:
        with open(file, "r") as loadedfile:
            contents = json.load(loadedfile)
            return contents

    except (OSError, IOError, ) as ex:
        err_message = "Unable to open '{}': {}".format(file, str(ex))
    except (json.decoder.JSONDecodeError) as ex:
        err_message = "Unable to parse '{}': {}".format(file, str(ex))
    if err_message:
        fail(err_message)

def output_results(results):
    """ Output results, or a message indicating there aren't any"""
    total_result_count = len(results)
    if total_result_count == 1:
        print("Search found 1 result")
    else:
        print("Search found {} results".format(total_result_count))
    truncated = False
    if total_result_count > MAX_RESULTS_SHOW:
        truncated = True
        results = itertools.islice(results, MAX_RESULTS_SHOW)
    for result in results:
        result.present()
        print()
    if truncated:
        print("Results were truncated to {} of {} entries".format(
            MAX_RESULTS_SHOW, total_result_count))
    if not results:
        print("No results found")

def cmd_search(commandline):
    """ Run a search and return results
    :param command: The command as a single string
    :return: A list of ResultValues
    :raises FailedException: When invalid input is entered"""
    results = []
    command = commandline.split(" ")
    if len(command) == 2:
        # Allow for empty matching by appending empty string
        command.append("")
    if len(command) < 3:
        fail("search command should be in the form: <search type> <field name> <match>")

    search_type_key = command[0]
    if search_type_key not in SEARCH_TYPES:
        fail("Invalid search type {}".format(search_type_key))
    search_type = SEARCH_TYPES[search_type_key]
    field_name = command[1]
    match_value = " ".join(command[2:])
    search_results = find_all(search_type, field_name, match_value)
    for search_result in search_results:
        if search_type_key == "users":
            results.append(create_user_result(search_result))
        elif search_type_key == "orgs":
            results.append(create_orgs_result(search_result))
        elif search_type_key == "tickets":
            results.append(create_tickets_result(search_result))
    return results

def create_tickets_result(ticketdict):
    """create_tickets_result - Create a tickets result gathering extra info
    :param ticketresult: The dictionary describing the ticket"""
    org_id = ticketdict.get(FIELD_ORGANIZATION_ID)
    assignee_id = ticketdict.get(FIELD_ASSIGNEE_ID)
    submitter_id = ticketdict.get(FIELD_SUBMITTER_ID)
    org_name = org_name_get(org_id)
    assignee = find_one_field(USERS, FIELD_ID, assignee_id, FIELD_NAME)
    submitter = find_one_field(USERS, FIELD_ID, submitter_id, FIELD_NAME)
    result_value = TicketResult(ticketdict, org_name, submitter, assignee)
    return result_value

def create_user_result(userdict):
    """create_user_result - Create a user result gathering extra info
    :param userdict: The dictionary describing the user
    """
    org_id = userdict.get(FIELD_ORGANIZATION_ID)
    orgname = org_name_get(org_id)

    user_id = userdict.get(FIELD_ID)
    submitted = field_from_values(find_all(TICKETS, FIELD_SUBMITTER_ID, user_id),
                                  FIELD_SUBJECT)
    assigned = field_from_values(find_all(TICKETS, FIELD_ASSIGNEE_ID, user_id),
                                 FIELD_SUBJECT)
    return UserResult(userdict, orgname, assigned, submitted)

def org_name_get(org_id):
    """Shortcut for getting an organization name"""
    return find_one_field(ORGS, FIELD_ID, org_id, FIELD_NAME)

class SearchCommands(cmd.Cmd):
    """Command definitions using python's cmd module"""
    def do_search(self, line):
        """Perform a search for:
    search users <field name> <value>
    search orgs <field name> <value>
    search tickets <field name> <value>"""
        try:
            results = cmd_search(line)
            output_results(results)
        except FailedException:
            #Failed exception means it's already handled
            pass

    def complete_search(self, text, line, begidx, endidx):
        """Perform tab completion help for search command
        """
        index = min(len(line[:begidx].split(" ")), 4)
        # Sometimes this function get's called for a subset of a command
        # I.E. 'text' begins midway through a command, not on a space boundary
        # This is annoying, but here we calculate the offset from the space boundary
        # to apply to strings to handle this.
        sub_offset = len(line[:endidx].split(" ")[-1]) - len(text)
        search_types = list(SEARCH_TYPES.keys())
        parts = line.split(" ")
        if index <= 2:
            # complete for search type
            return list(filter(lambda search_type: search_type.startswith(text),
                               (search_type[sub_offset:] for search_type in search_types)))
        elif index == 3:
            # Complete for field of a search type
            typename = parts[1]
            if typename in SEARCH_TYPES:
                fields = SEARCH_TYPES[typename].fields.keys()
                return list(filter(lambda field: field.startswith(text),
                                   (field[sub_offset:] for field in fields)))
        elif index >= 4:
            # Complete for value
            # We need to go back and always compare the values with the full value
            # from the start of the field
            field_start_offset = len(" ".join(parts[:3])) + 1 # Add 1 for the missing space
            field_starts_with = line[field_start_offset:endidx]
            cut_first_chars = len(field_starts_with) - len(text)
            #Recombine for searching to allow search string to have spaces
            typename = parts[1]
            field_name = parts[2]
            if typename not in SEARCH_TYPES:
                return ""
            if field_name in SEARCH_TYPES[typename].fields.keys():
                # Show all values of the field that start with the current string
                # Setup a chain to select only the parts of the fields that match the
                # requsted tab completion
                field_values = (str(value[field_name]) for value in SEARCH_TYPES[typename].values)
                matching_entries = filter(lambda x: x.startswith(field_starts_with),
                                          field_values)
                truncated_matching_entry_list = [x[cut_first_chars:] for x in matching_entries]   
                return truncated_matching_entry_list
        return ""

    def do_EOF(self, line):
        """Exit"""
        self.do_exit(line)

    def do_exit(self, _):
        """Exit from interactive mode"""
        raise ExitException()


def do_interactive():
    """Start interactive mode with a command input loop"""
    intro = """Welcome to Tom's searcher

The following commands are available:

    search users <field name> <exact match>
    search orgs <field name> <exact match>
    search tickets <field name> <exact match>
    help [<command>]
    exit

Use TAB to complete any field.
"""
    try:
        SearchCommands().cmdloop(intro=intro)
    except ExitException:
        pass
    return

def do_init():
    """Load files into global variables
    :raises FailedException: When there is an issue loading a file"""
    global ORGS
    global TICKETS
    global USERS
    global SEARCH_TYPES
    ORGS = ValidatedDictList("organizations.json",
        "tickets", {
            "_id": int,
            "url": str,
            "external_id": str,
            "name": str,
            "domain_names": list,
            "created_at": str,
            "details": str,
            "shared_tickets": bool,
            "tags": list,
        })
    TICKETS = ValidatedDictList("tickets.json",
        "tickets", {
            "_id": str,
            "url": str,
            "external_id": str,
            "created_at": str,
            "type": str,
            "subject": str,
            "description": str,
            "priority": str,
            "status": str,
            "submitter_id": int,
            "assignee_id": int,
            "organization_id": int,
            "tags": list,
            "has_incidents": bool,
            "due_at": str,
            "via": str
        })
    USERS = ValidatedDictList("users.json",
        "users", {
            "_id": int,
            "url": str,
            "external_id": str,
            "name": str,
            "alias": str,
            "created_at":str,
            "active": bool,
            "verified": bool,
            "shared": bool,
            "locale": str,
            "timezone": str,
            "last_login_at": str,
            "email": str,
            "phone": str,
            "signature": str,
            "organization_id": int,
            "tags": list,
            "suspended": bool,
            "role": str
        })

    SEARCH_TYPES = {
        "users": USERS,
        "orgs": ORGS,
        "tickets": TICKETS,
}

class TestTabCompletion(unittest.TestCase):
    """Python unittest for tab completion"""
    def setUp(self):
        do_init()

    @staticmethod
    def tab_complete(stext, base):
        """Shortcut for calling search tab completion
        :param stext: The text that needs to be completed
        :param base: The base text for the search that doesn't need to be completed"""
        base_len = len(base)
        return SearchCommands().complete_search(
            stext, base + stext, base_len, base_len + len(stext))

    def test_tab_completion_search_types(self):
        """Test tab completion for search types"""
        f = TestTabCompletion.tab_complete
        self.assertSetEqual(set(f("", "search ")), set(["users", "tickets", "orgs"]))
        self.assertSetEqual(set(f("us", "search ")), set(["users"]))
        self.assertSetEqual(set(f("user", "search ")), set(["users"]))
        self.assertSetEqual(set(f("usasfadsf", "search ")), set([]))

    def test_tab_completion_search_keys(self):
        """Test tab completion for field key names"""
        f = TestTabCompletion.tab_complete
        self.assertSetEqual(set(f("","search users ")), set(SEARCH_TYPES["users"].fields.keys()))
        self.assertSetEqual(set(f("t","search users ")), set(["timezone", "tags"]))
        self.assertSetEqual(set(f("tags","search users ")), set(["tags"]))
        self.assertSetEqual(set(f("tasfdsfads","search users")), set())

    def test_tab_completion_search_values(self):
        """Test value completion. These rely on the provided json files contents"""
        f = TestTabCompletion.tab_complete
        self.assertEqual(len(f("", "search users tags ")), 75)
        self.assertEqual(len(f("['", "search users tags ")), 75)
        self.assertEqual(len(f("['V", "search users tags ")), 4)
        self.assertEqual(len(f("['Veg", "search users tags ")), 1)
        self.assertEqual(len(f("dfdfsd", "search users tags ")), 0)

    def test_search(self):
        """Test search functionality with loaded default data"""
        #Cmd string too short
        with self.assertRaises(FailedException):
            cmd_search("users")
        # Invalid search type
        with self.assertRaises(FailedException):
            cmd_search("cats _id 1")
        #Invalid search field
        with self.assertRaises(FailedException):
            cmd_search("users _not_valid 5")
        # Test searching empty value
        self.assertListEqual(cmd_search("users tags "), list())
        # Test basic single search
        self.assertEqual(len(cmd_search("users _id 1")), 1)
        # Test that related ticket data is retrieved
        self.assertEqual(len(list(cmd_search("users _id 1")[0].assigned_ticket_names)), 2)
        # Test a search where records contain empty data
        self.assertEqual(cmd_search("users _id 11")[0].valuedict["email"], "")
        self.assertEqual(len(list(cmd_search("users email"))), 2)
        self.assertEqual(cmd_search("users _id 16")[0].org_name, "None Found")
        # Test searching orgs
        self.assertEqual(len(list(cmd_search("orgs _id 101"))), 1)
        self.assertEqual(len(list(cmd_search("orgs _id 1"))), 0)
        # Test searching tags
        self.assertEqual(len(list(cmd_search("tickets _id 1"))), 0)

class TestValidatedDictList(unittest.TestCase):
    """Test data loading and parsing"""
    def test_ValididatedDict_List_init(self):
        # Test bad json parse
        with self.assertRaises(FailedException):
            ValidatedDictList("test-invalid.json", "test-invalid", {})
        # Test missing file
        with self.assertRaises(FailedException):
            ValidatedDictList("test-nosuchfile.json", "test-invalid", {})
        # Test incorrect data type
        with self.assertRaises(FailedException):
            # Valid json invalid type expected
            ValidatedDictList("test-valid.json", "test-valid", {"test_int": str, "test_string":str})
        # Test working data
        valid = ValidatedDictList("test-valid.json", "test-valid", {"id": int, "test_int": int, "test_string":str,
                                                                    "test_missing": int, "test_missing_id": int})
        # Test data was loaded correctly
        self.assertIsInstance(valid, ValidatedDictList)
        self.assertEqual(len(valid.values), 2)
        self.assertEqual(valid.values[0][FIELD_ID], 1)
        self.assertEqual(valid.values[0]["test_int"], 123)
        self.assertEqual(valid.values[0]["test_string"], "string")
        self.assertEqual(valid.values[0]["test_missing"], 0)
        self.assertEqual(valid.values[0]["test_missing_id"], None)
        # Test that find one fails where there are multiple entries
        with self.assertRaises(FailedException):
            find_one_field(valid, "test_int", 123, FIELD_ID)
        # Test that find one works for standard case
        value = find_one_field(valid, "test_string", "string", FIELD_ID)
        self.assertEqual(value, 1)

if __name__ == "__main__":
    try:
        do_init()
        do_interactive()
    except FailedException:
        # Don't mess up the console with a FailedException
        # Error message is already printed
        pass
